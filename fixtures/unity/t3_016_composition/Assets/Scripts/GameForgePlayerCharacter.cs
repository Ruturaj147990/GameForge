using UnityEngine;

namespace GameForge.Gameplay
{
    /// <summary>
    /// Composed Player Character integrating CharacterController, HealthComponent,
    /// StaminaComponent, and IPickupReceiver.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public class GameForgePlayerCharacter : MonoBehaviour, IPickupReceiver
    {
        [Header("Movement & Kinematics")]
        public float maxWalkSpeed = 6.0f; // m/s
        public float maxAcceleration = 40.0f; // m/s^2
        public float brakingDeceleration = 55.0f; // m/s^2
        public float jumpHeight = 1.2f; // m

        [Header("Resource Components")]
        [SerializeField] private HealthComponent healthComponent;
        [SerializeField] private StaminaComponent staminaComponent;

        public HealthComponent Health => healthComponent;
        public StaminaComponent Stamina => staminaComponent;

        private void Awake()
        {
            if (healthComponent == null)
            {
                healthComponent = GetComponent<HealthComponent>();
                if (healthComponent == null)
                {
                    healthComponent = gameObject.AddComponent<HealthComponent>();
                }
            }

            if (staminaComponent == null)
            {
                staminaComponent = GetComponent<StaminaComponent>();
                if (staminaComponent == null)
                {
                    staminaComponent = gameObject.AddComponent<StaminaComponent>();
                }
            }
        }

        public bool CanReceiveResource(ResourceType type, float amount)
        {
            switch (type)
            {
                case ResourceType.Health:
                    return healthComponent != null && healthComponent.IsAlive && healthComponent.CurrentHealth < healthComponent.MaxHealth;
                case ResourceType.Stamina:
                    return staminaComponent != null && staminaComponent.CurrentStamina < staminaComponent.MaxStamina;
                default:
                    return false;
            }
        }

        public bool ReceiveResource(ResourceType type, float amount)
        {
            switch (type)
            {
                case ResourceType.Health:
                    return healthComponent != null && healthComponent.ApplyHealing(amount);
                case ResourceType.Stamina:
                    return staminaComponent != null && staminaComponent.ApplyStaminaRestoration(amount);
                default:
                    return false;
            }
        }
    }
}
