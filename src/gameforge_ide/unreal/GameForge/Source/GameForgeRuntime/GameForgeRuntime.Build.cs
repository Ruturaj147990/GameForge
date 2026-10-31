// Copyright 2026 GameForge Systems. All Rights Reserved.

using UnrealBuildTool;

/** Runtime gameplay types usable from game Blueprints and packaged builds. */
public class GameForgeRuntime : ModuleRules
{
	public GameForgeRuntime(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "AIModule", "GameplayTasks", "NavigationSystem" });
		PrivateDependencyModuleNames.AddRange(new string[] { "UMG", "Slate", "SlateCore", "Niagara", "Json" });
	}
}
