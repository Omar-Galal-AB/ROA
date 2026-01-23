// Copyright ROA Development Team. All Rights Reserved.

using UnrealBuildTool;
using System.IO;

public class ROA : ModuleRules
{
	public ROA(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
		
		// Use C++20 (UE 5.6 requirement)
		CppStandard = CppStandardVersion.Cpp20;
		
		// Get ThirdParty folder path
		string ThirdPartyPath = Path.Combine(ModuleDirectory, "../../ThirdParty");
		
		PublicIncludePaths.AddRange(
			new string[] {
				// Add public include paths here
			}
		);
				
		
		PrivateIncludePaths.AddRange(
			new string[] {
				// Add private include paths here
			}
		);
			
		
		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"InputCore",
				"Slate",
				"SlateCore",
				"UMG",
				// ... add other public dependencies that you statically link with here ...
			}
		);
			
		
		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				// Networking modules
				"Sockets",
				"Networking",
				"HTTP",
				"WebSockets",
				
				// Serialization
				"Json",
				"JsonUtilities",
				"XmlParser",  // For URDF parsing
				
				// Physics
				"PhysicsCore",
				"Chaos",
				
				// Rendering (for visualization)
				"RenderCore",
				"RHI",
				
				// Asset management
				"AssetRegistry",
				"UnrealEd",  // For editor features
				
				// Editor-only modules for FTI (File Type Integration)
				"EditorFramework",
				"Kismet",  // For blueprint creation
				"KismetCompiler",
				"BlueprintGraph",
				"Projects",  // For project settings
				
				// Python scripting (for FTI hierarchy assembly)
				"PythonScriptPlugin",
				
				// Menu and toolbar integration
				"LevelEditor",
				"ToolMenus",
				"DesktopPlatform",
				"ApplicationCore",
				
				// ... add private dependencies that you statically link with here ...	
			}
		);
		
		
		DynamicallyLoadedModuleNames.AddRange(
			new string[]
			{
				// ... add any modules that your module loads dynamically here ...
			}
		);
		
		// Platform specific settings
		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			// Windows specific dependencies
			SetupROS2ThirdParty_Windows(ThirdPartyPath);
		}
		else if (Target.Platform == UnrealTargetPlatform.Linux)
		{
			// Linux specific dependencies
			SetupROS2ThirdParty_Linux();
		}
		
		// Enable RTTI for JSON parsing and advanced features
		bUseRTTI = true;
		
		// Enable exceptions for error handling
		bEnableExceptions = true;
		
		// Optimization settings
		OptimizeCode = CodeOptimization.InShippingBuildsOnly;
	}
	
	// ========================================================================
	// ROS2 ThirdParty Integration (Windows)
	// ========================================================================
	private void SetupROS2ThirdParty_Windows(string ThirdPartyPath)
	{
		// TEMPORARILY DISABLED: Native ROS2 DLL loading issues at startup
		// The ROS2 DLLs are loaded before the module's StartupModule() runs,
		// so we can't add the DLL path in time. 
		// 
		// To fix: Add the ROS2 bin path to system PATH before launching UE5
		// Or copy all DLLs to the Binaries folder manually
		
		System.Console.WriteLine("ROA: TCP network mode (use dual-port architecture)");
		PublicDefinitions.Add("ROA_NATIVE_ROS2=0");
	}
	
	// ========================================================================
	// ROS2 ThirdParty Integration (Linux)
	// ========================================================================
	private void SetupROS2ThirdParty_Linux()
	{
		// On Linux, use system ROS2 installation
		string ROS2DistroPath = "/opt/ros/humble";
		
		if (Directory.Exists(ROS2DistroPath))
		{
			System.Console.WriteLine("ROA: Native ROS2 mode enabled (system ROS2 Humble found)");
			
			// Add system ROS2 paths
			PublicIncludePaths.Add(Path.Combine(ROS2DistroPath, "include"));
			PublicAdditionalLibraries.Add(Path.Combine(ROS2DistroPath, "lib", "librclcpp.so"));
			PublicAdditionalLibraries.Add(Path.Combine(ROS2DistroPath, "lib", "librcl.so"));
			PublicAdditionalLibraries.Add(Path.Combine(ROS2DistroPath, "lib", "librmw.so"));
			PublicAdditionalLibraries.Add(Path.Combine(ROS2DistroPath, "lib", "libfastrtps.so"));
			
			RuntimeDependencies.Add(Path.Combine(ROS2DistroPath, "lib", "librclcpp.so"));
			RuntimeDependencies.Add(Path.Combine(ROS2DistroPath, "lib", "librcl.so"));
			
			PublicDefinitions.Add("ROA_NATIVE_ROS2=1");
		}
		else
		{
			System.Console.WriteLine("ROA: TCP fallback mode (ROS2 not installed)");
			PublicDefinitions.Add("ROA_NATIVE_ROS2=0");
		}
	}
}
