#!/usr/bin/env python3
"""
ROA XACRO Processor - Embedded Python Backend
Converts XACRO files to URDF using the xacro Python package
"""

import sys
import os

def main():
    if len(sys.argv) != 3:
        print("Usage: xacro_processor.py <input.xacro> <output.urdf>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Check input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"ROA XACRO Processor: Converting {input_file} to {output_file}")
    
    try:
        # Try to import xacro
        import xacro
        
        # Process XACRO file
        doc = xacro.process_file(input_file)
   
        # Get URDF string
        urdf_string = doc.toprettyxml(indent='  ')
        
        # Write to output file
        with open(output_file, 'w') as f:
            f.write(urdf_string)
        
        print(f"Success: URDF written to {output_file}")
        sys.exit(0)
        
    except ImportError as e:
        print(f"Error: XACRO package not installed")
        print(f"Install with: pip install xacro")
        print(f"Details: {e}")
        sys.exit(1)
    
    except Exception as e:
        print(f"Error: XACRO processing failed")
        print(f"Details: {e}")
    sys.exit(1)

if __name__ == "__main__":
    main()
