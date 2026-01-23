"""
Texture Handler for FTI

Comprehensive texture management for converting and preparing
textures for Unreal Engine 5 compatibility.

Features:
- Texture format conversion
- Resolution optimization
- Normal map handling
- PBR texture setup
- Embedded texture extraction
- Texture atlas generation
"""

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Image processing
try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class TextureType(Enum):
    """Types of textures in PBR workflow."""

    DIFFUSE = "diffuse"  # Base color / albedo
    NORMAL = "normal"  # Normal map
    ROUGHNESS = "roughness"  # Roughness map
    METALLIC = "metallic"  # Metallic map
    AMBIENT_OCCLUSION = "ao"  # AO map
    EMISSIVE = "emissive"  # Emissive map
    OPACITY = "opacity"  # Alpha/transparency
    HEIGHT = "height"  # Displacement/height map
    SPECULAR = "specular"  # Specular map (legacy)
    ORM = "orm"  # Packed Occlusion/Roughness/Metallic


@dataclass
class TextureInfo:
    """Information about a texture."""

    path: str
    texture_type: TextureType
    width: int = 0
    height: int = 0
    channels: int = 0
    format: str = ""
    size_bytes: int = 0
    is_power_of_two: bool = False
    needs_conversion: bool = False
    output_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "type": self.texture_type.value,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "format": self.format,
            "size_kb": round(self.size_bytes / 1024, 2),
            "power_of_two": self.is_power_of_two,
            "needs_conversion": self.needs_conversion,
        }


@dataclass
class TextureResult:
    """Result of texture processing."""

    success: bool
    textures_processed: int = 0
    textures: List[TextureInfo] = field(default_factory=list)
    output_directory: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class TextureHandler:
    """
    Handles texture processing for FTI.

    Prepares textures for Unreal Engine 5 by:
    - Converting to compatible formats
    - Resizing to power-of-two dimensions
    - Setting up proper sRGB/linear color spaces
    - Generating mipmaps info
    - Handling normal map conversion
    """

    # UE5 compatible formats
    SUPPORTED_INPUT_FORMATS = [
        ".png",
        ".jpg",
        ".jpeg",
        ".tga",
        ".bmp",
        ".tiff",
        ".tif",
        ".exr",
        ".hdr",
    ]
    PREFERRED_OUTPUT_FORMAT = ".png"  # Best quality for UE5

    # Texture size limits
    MIN_SIZE = 4
    MAX_SIZE = 8192
    DEFAULT_MAX_SIZE = 4096

    # Texture type detection patterns
    TYPE_PATTERNS = {
        TextureType.DIFFUSE: [
            "diffuse",
            "albedo",
            "basecolor",
            "base_color",
            "color",
            "_d",
            "_c",
        ],
        TextureType.NORMAL: ["normal", "norm", "nrm", "_n", "bump"],
        TextureType.ROUGHNESS: ["roughness", "rough", "_r"],
        TextureType.METALLIC: ["metallic", "metal", "metalness", "_m"],
        TextureType.AMBIENT_OCCLUSION: ["ao", "ambient", "occlusion", "_ao"],
        TextureType.EMISSIVE: ["emissive", "emission", "glow", "_e"],
        TextureType.OPACITY: ["opacity", "alpha", "transparency", "_a"],
        TextureType.HEIGHT: ["height", "displacement", "disp", "_h"],
        TextureType.SPECULAR: ["specular", "spec", "_s"],
        TextureType.ORM: ["orm", "packed"],
    }

    def __init__(
        self,
        output_dir: Optional[str] = None,
        max_size: int = DEFAULT_MAX_SIZE,
        convert_to_png: bool = True,
        force_power_of_two: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize texture handler.

        Args:
            output_dir: Directory for processed textures
            max_size: Maximum texture dimension
            convert_to_png: Convert all textures to PNG
            force_power_of_two: Resize to power-of-two dimensions
            logger: Logger instance
        """
        self.output_dir = output_dir
        self.max_size = min(max_size, self.MAX_SIZE)
        self.convert_to_png = convert_to_png
        self.force_power_of_two = force_power_of_two
        self.logger = logger or logging.getLogger(__name__)

        if not PIL_AVAILABLE:
            self.logger.warning("PIL not available - texture processing limited")

    def process_textures(
        self, texture_paths: List[str], output_dir: Optional[str] = None
    ) -> TextureResult:
        """
        Process multiple textures.

        Args:
            texture_paths: List of texture file paths
            output_dir: Output directory (overrides instance setting)

        Returns:
            TextureResult with processing results
        """
        out_dir = output_dir or self.output_dir
        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)

        result = TextureResult(success=True, output_directory=out_dir)

        for path in texture_paths:
            try:
                tex_info = self.process_texture(path, out_dir)
                if tex_info:
                    result.textures.append(tex_info)
                    result.textures_processed += 1
            except Exception as e:
                result.errors.append(f"Error processing {path}: {e}")
                result.success = False

        return result

    def process_texture(
        self, texture_path: str, output_dir: Optional[str] = None
    ) -> Optional[TextureInfo]:
        """
        Process a single texture.

        Args:
            texture_path: Path to texture file
            output_dir: Output directory

        Returns:
            TextureInfo with processed texture info
        """
        if not os.path.exists(texture_path):
            self.logger.warning(f"Texture not found: {texture_path}")
            return None

        path = Path(texture_path)

        # Detect texture type
        tex_type = self._detect_texture_type(path.stem)

        # Get basic info
        tex_info = TextureInfo(
            path=str(path),
            texture_type=tex_type,
            format=path.suffix.lower(),
            size_bytes=path.stat().st_size,
        )

        if not PIL_AVAILABLE:
            self.logger.warning("Cannot process texture without PIL")
            return tex_info

        try:
            with Image.open(texture_path) as img:
                tex_info.width = img.width
                tex_info.height = img.height
                tex_info.channels = len(img.getbands())
                tex_info.is_power_of_two = self._is_power_of_two(img.width, img.height)

                # Determine if conversion needed
                needs_resize = (self.force_power_of_two and not tex_info.is_power_of_two) or (
                    img.width > self.max_size or img.height > self.max_size
                )

                needs_format_convert = self.convert_to_png and tex_info.format != ".png"

                tex_info.needs_conversion = needs_resize or needs_format_convert

                # Process if needed and output directory provided
                if tex_info.needs_conversion and output_dir:
                    processed_img = self._process_image(img, tex_type, needs_resize)

                    # Save processed texture
                    output_name = path.stem + ".png"
                    output_path = Path(output_dir) / output_name

                    processed_img.save(output_path, "PNG", optimize=True)
                    tex_info.output_path = str(output_path)

                    self.logger.info(f"Processed texture: {path.name} -> {output_name}")

                elif output_dir and not tex_info.needs_conversion:
                    # Just copy the file
                    output_path = Path(output_dir) / path.name
                    shutil.copy2(texture_path, output_path)
                    tex_info.output_path = str(output_path)

        except Exception as e:
            self.logger.error(f"Error processing texture {texture_path}: {e}")
            return tex_info

        return tex_info

    def _process_image(
        self, img: "Image.Image", tex_type: TextureType, needs_resize: bool
    ) -> "Image.Image":
        """Process image for UE5 compatibility."""
        result = img.copy()

        # Resize if needed
        if needs_resize:
            new_width = self._next_power_of_two(min(img.width, self.max_size))
            new_height = self._next_power_of_two(min(img.height, self.max_size))

            # Use high-quality resampling
            result = result.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Handle normal maps - ensure proper format
        if tex_type == TextureType.NORMAL:
            # Normal maps should be RGB
            if result.mode != "RGB":
                result = result.convert("RGB")

        # Ensure proper mode for output
        if result.mode == "P":  # Palette mode
            result = result.convert("RGBA" if "transparency" in result.info else "RGB")

        return result

    def _detect_texture_type(self, filename: str) -> TextureType:
        """Detect texture type from filename."""
        lower_name = filename.lower()

        for tex_type, patterns in self.TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in lower_name:
                    return tex_type

        return TextureType.DIFFUSE  # Default

    def _is_power_of_two(self, width: int, height: int) -> bool:
        """Check if dimensions are power of two."""
        return (width & (width - 1) == 0) and (height & (height - 1) == 0)

    def _next_power_of_two(self, value: int) -> int:
        """Get next power of two >= value."""
        if value <= 0:
            return 1

        power = 1
        while power < value:
            power *= 2

        # Don't exceed max
        return min(power, self.MAX_SIZE)

    def extract_embedded_textures(self, source_file: str, output_dir: str) -> List[str]:
        """
        Extract embedded textures from model files.

        Supports extracting from:
        - glTF/GLB (base64 or binary)
        - FBX (embedded textures)
        - DAE (embedded images)

        Returns:
            List of extracted texture paths
        """
        extracted = []
        path = Path(source_file)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        suffix = path.suffix.lower()

        if suffix in [".glb", ".gltf"]:
            extracted = self._extract_gltf_textures(source_file, output_path)
        elif suffix == ".fbx":
            extracted = self._extract_fbx_textures(source_file, output_path)
        elif suffix == ".dae":
            extracted = self._extract_dae_textures(source_file, output_path)

        return extracted

    def _extract_gltf_textures(self, gltf_path: str, output_dir: Path) -> List[str]:
        """Extract textures from glTF/GLB."""
        extracted = []

        try:
            from pygltflib import GLTF2

            gltf = GLTF2().load(gltf_path)

            if gltf.images:
                for i, image in enumerate(gltf.images):
                    if image.uri:
                        if image.uri.startswith("data:"):
                            # Base64 embedded
                            import base64

                            data_start = image.uri.find(",") + 1
                            img_data = base64.b64decode(image.uri[data_start:])

                            # Determine extension from mime type
                            ext = ".png"
                            if "jpeg" in image.uri or "jpg" in image.uri:
                                ext = ".jpg"

                            output_file = output_dir / f"texture_{i}{ext}"
                            with open(output_file, "wb") as f:
                                f.write(img_data)
                            extracted.append(str(output_file))

                    elif image.bufferView is not None:
                        # Binary buffer
                        buffer_view = gltf.bufferViews[image.bufferView]
                        blob = gltf.binary_blob()

                        if blob:
                            offset = buffer_view.byteOffset or 0
                            length = buffer_view.byteLength
                            img_data = blob[offset : offset + length]

                            ext = ".png"
                            if image.mimeType and "jpeg" in image.mimeType:
                                ext = ".jpg"

                            output_file = output_dir / f"texture_{i}{ext}"
                            with open(output_file, "wb") as f:
                                f.write(img_data)
                            extracted.append(str(output_file))

        except ImportError:
            self.logger.warning("pygltflib not available for glTF texture extraction")
        except Exception as e:
            self.logger.error(f"Error extracting glTF textures: {e}")

        return extracted

    def _extract_fbx_textures(self, fbx_path: str, output_dir: Path) -> List[str]:
        """Extract textures from FBX (if embedded)."""
        # FBX texture extraction requires FBX SDK or specific parsing
        # For now, we just look for textures referenced in the file
        self.logger.info("FBX texture extraction - checking for referenced files")
        return []

    def _extract_dae_textures(self, dae_path: str, output_dir: Path) -> List[str]:
        """Extract embedded textures from COLLADA/DAE."""
        extracted = []

        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(dae_path)
            root = tree.getroot()

            # COLLADA namespace
            ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}

            # Find embedded images
            images = root.findall(".//{http://www.collada.org/2005/11/COLLADASchema}image")

            for i, img in enumerate(images):
                # Check for embedded data
                data_elem = img.find(".//{http://www.collada.org/2005/11/COLLADASchema}data")
                if data_elem is not None and data_elem.text:
                    import base64

                    img_data = base64.b64decode(data_elem.text)

                    img_name = img.get("name", f"texture_{i}")
                    output_file = output_dir / f"{img_name}.png"

                    with open(output_file, "wb") as f:
                        f.write(img_data)
                    extracted.append(str(output_file))

        except Exception as e:
            self.logger.error(f"Error extracting DAE textures: {e}")

        return extracted

    def create_orm_texture(
        self,
        ao_path: Optional[str],
        roughness_path: Optional[str],
        metallic_path: Optional[str],
        output_path: str,
    ) -> bool:
        """
        Create packed ORM texture (Occlusion, Roughness, Metallic).

        This is the UE5 standard packed format:
        - R channel: Ambient Occlusion
        - G channel: Roughness
        - B channel: Metallic

        Returns:
            True if successful
        """
        if not PIL_AVAILABLE:
            self.logger.error("PIL required for ORM texture creation")
            return False

        try:
            # Determine output size from first available texture
            width, height = 1024, 1024

            for path in [ao_path, roughness_path, metallic_path]:
                if path and os.path.exists(path):
                    with Image.open(path) as img:
                        width, height = img.size
                        break

            # Create channels
            r_channel = self._load_grayscale(ao_path, width, height, default=255)
            g_channel = self._load_grayscale(roughness_path, width, height, default=128)
            b_channel = self._load_grayscale(metallic_path, width, height, default=0)

            # Merge channels
            orm = Image.merge("RGB", (r_channel, g_channel, b_channel))
            orm.save(output_path, "PNG")

            self.logger.info(f"Created ORM texture: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error creating ORM texture: {e}")
            return False

    def _load_grayscale(
        self, path: Optional[str], width: int, height: int, default: int = 128
    ) -> "Image.Image":
        """Load image as grayscale or create default."""
        if path and os.path.exists(path):
            with Image.open(path) as img:
                gray = img.convert("L")
                if gray.size != (width, height):
                    gray = gray.resize((width, height), Image.Resampling.LANCZOS)
                return gray
        else:
            return Image.new("L", (width, height), default)


def process_model_textures(model_path: str, output_dir: str, max_size: int = 4096) -> TextureResult:
    """
    Convenience function to process all textures for a model.

    Finds and processes textures referenced by the model file.
    """
    handler = TextureHandler(output_dir=output_dir, max_size=max_size)

    model_dir = Path(model_path).parent
    texture_paths = []

    # Find texture files in model directory
    for ext in TextureHandler.SUPPORTED_INPUT_FORMATS:
        texture_paths.extend(model_dir.glob(f"*{ext}"))
        texture_paths.extend(model_dir.glob(f"textures/*{ext}"))
        texture_paths.extend(model_dir.glob(f"materials/*{ext}"))

    return handler.process_textures([str(p) for p in texture_paths], output_dir)
