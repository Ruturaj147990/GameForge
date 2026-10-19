using System;
using UnityEngine;

namespace GameForge.Benchmark
{
    public enum PickupType
    {
        Health,
        Stamina
    }

    public class PickupComponent : MonoBehaviour
    {
        public PickupType pickupType = PickupType.Health;
        public float restorationAmount = 25.0f;

        [SerializeField] private bool isConsumed = false;
        [SerializeField] private bool isActive = true;

        public event Action<GameObject, PickupType, float> OnPickupCollected;

        public bool IsConsumed => isConsumed;
        public bool IsActive => isActive;

        private bool isProcessingCollection = false;

        public bool AttemptCollect(GameObject collector)
        {
            if (!isActive || isConsumed || isProcessingCollection || collector == null)
            {
                return false;
            }

            if (float.IsNaN(restorationAmount) || float.IsInfinity(restorationAmount) || restorationAmount <= 0.0f)
            {
                return false;
            }

            isProcessingCollection = true;

            bool effectApplied = false;
            ResourceType targetRes = (pickupType == PickupType.Health) ? ResourceType.Health : ResourceType.Stamina;

            IPickupReceiver receiver = collector.GetComponent<IPickupReceiver>();
            if (receiver != null)
            {
                if (receiver.CanReceiveResource(targetRes, restorationAmount))
                {
                    effectApplied = receiver.ReceiveResource(targetRes, restorationAmount);
                }
            }
            else
            {
                if (pickupType == PickupType.Health)
                {
                    HealthComponent hc = collector.GetComponent<HealthComponent>();
                    if (hc != null && hc.IsAlive && hc.CurrentHealth < hc.MaxHealth)
                    {
                        effectApplied = hc.ApplyHealing(restorationAmount);
                    }
                }
                else if (pickupType == PickupType.Stamina)
                {
                    StaminaComponent sc = collector.GetComponent<StaminaComponent>();
                    if (sc != null && sc.CurrentStamina < sc.MaxStamina)
                    {
                        effectApplied = sc.ApplyStaminaRestoration(restorationAmount);
                    }
                }
            }

            if (effectApplied)
            {
                isConsumed = true;
                isActive = false;
                isProcessingCollection = false;
                OnPickupCollected?.Invoke(collector, pickupType, restorationAmount);
                return true;
            }

            isProcessingCollection = false;
            return false;
        }

        public void ResetPickupState()
        {
            isConsumed = false;
            isActive = true;
            isProcessingCollection = false;
        }
    }
}
