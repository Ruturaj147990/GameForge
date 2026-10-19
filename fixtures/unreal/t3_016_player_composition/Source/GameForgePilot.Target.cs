using UnrealBuildTool;
using System.Collections.Generic;

public class GameForgePilotTarget : TargetRules
{
    public GameForgePilotTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("GameForgePilot");
    }
}
