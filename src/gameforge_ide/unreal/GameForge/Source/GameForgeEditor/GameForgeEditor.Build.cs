// Copyright 2026 GameForge Systems. All Rights Reserved.

using UnrealBuildTool;

public class GameForgeEditor : ModuleRules
{
	public GameForgeEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicIncludePaths.AddRange(
			new string[] {
				// Public include paths
			}
		);

		PrivateIncludePaths.AddRange(
			new string[] {
				// Private include paths
			}
		);

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"HTTP",
				"Json",
				"JsonUtilities",
				"GameForgeRuntime"
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"UnrealEd",
				"Slate",
				"SlateCore",
				"InputCore",
				"EditorSubsystem",
				"ToolMenus",
				"BlueprintGraph",
				"KismetCompiler",
				"Kismet",
				"AssetTools",
				"UMG",
				"UMGEditor",
				"Landscape",
				"Foliage",
				"NavigationSystem",
				"AIModule",
				"Niagara"
			}
		);
	}
}
