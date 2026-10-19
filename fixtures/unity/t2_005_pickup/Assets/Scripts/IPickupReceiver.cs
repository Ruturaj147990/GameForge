using UnityEngine;

namespace GameForge.Benchmark
{
    public enum ResourceType
    {
        Health,
        Stamina,
        Generic
    }

    public interface IPickupReceiver
    {
        bool CanReceiveResource(ResourceType type, float amount);
        bool ReceiveResource(ResourceType type, float amount);
    }
}
