using System;
using UnityEngine;
using UnityEngine.UI;

namespace GameForge.Benchmark
{
    /// <summary>
    /// Reference implementation of Health and Stamina HUD for Unity (T3-017).
    /// Follows GameForge HUD specification:
    /// - Displays current and max health/stamina
    /// - Clamps normalized progress safely in [0.0, 1.0]
    /// - Event-driven updates from Health and Stamina components
    /// - Subscribes and cleanly unsubscribes; guards against duplicate subscriptions
    /// - Handles null player references and player rebinding safely
    /// </summary>
    public class HealthStaminaHUD : MonoBehaviour
    {
        [Header("UI Elements")]
        public Text healthLabel;
        public Image healthBar;
        public Text staminaLabel;
        public Image staminaBar;

        [Header("Runtime Display Values")]
        [SerializeField] private float displayedHealth = 100.0f;
        [SerializeField] private float maxHealth = 100.0f;
        [SerializeField] private float healthPercent = 1.0f;
        [SerializeField] private float displayedStamina = 100.0f;
        [SerializeField] private float maxStamina = 100.0f;
        [SerializeField] private float staminaPercent = 1.0f;
        [SerializeField] private bool isDead = false;
        [SerializeField] private bool isBound = false;

        private HealthComponent boundHealthComponent;
        private StaminaComponent boundStaminaComponent;

        public float DisplayedHealth => displayedHealth;
        public float HealthPercent => healthPercent;
        public float DisplayedStamina => displayedStamina;
        public float StaminaPercent => staminaPercent;
        public bool IsDead => isDead;
        public bool IsBound => isBound;

        private void OnDestroy()
        {
            UnbindFromPlayer();
        }

        public void BindToPlayer(GameObject playerObject)
        {
            if (playerObject == null)
            {
                return;
            }

            var healthComp = playerObject.GetComponent<HealthComponent>();
            var staminaComp = playerObject.GetComponent<StaminaComponent>();
            BindToComponents(healthComp, staminaComp);
        }

        public void BindToComponents(HealthComponent healthComp, StaminaComponent staminaComp)
        {
            if (isBound)
            {
                UnbindFromPlayer();
            }

            boundHealthComponent = healthComp;
            boundStaminaComponent = staminaComp;

            if (boundHealthComponent != null)
            {
                maxHealth = boundHealthComponent.MaxHealth;
                displayedHealth = boundHealthComponent.CurrentHealth;
                isDead = boundHealthComponent.IsDead;

                boundHealthComponent.OnHealthChanged += HandleHealthChanged;
                boundHealthComponent.OnDeath += HandleDeath;
            }

            if (boundStaminaComponent != null)
            {
                maxStamina = boundStaminaComponent.MaxStamina;
                displayedStamina = boundStaminaComponent.CurrentStamina;

                boundStaminaComponent.OnStaminaChanged += HandleStaminaChanged;
            }

            isBound = (boundHealthComponent != null || boundStaminaComponent != null);
            RefreshDisplay();
        }

        public void UnbindFromPlayer()
        {
            if (boundHealthComponent != null)
            {
                boundHealthComponent.OnHealthChanged -= HandleHealthChanged;
                boundHealthComponent.OnDeath -= HandleDeath;
                boundHealthComponent = null;
            }

            if (boundStaminaComponent != null)
            {
                boundStaminaComponent.OnStaminaChanged -= HandleStaminaChanged;
                boundStaminaComponent = null;
            }

            isBound = false;
        }

        private void HandleHealthChanged(float newHealth, float delta)
        {
            displayedHealth = newHealth;
            if (displayedHealth <= 0.0f)
            {
                isDead = true;
            }
            RefreshDisplay();
        }

        private void HandleDeath()
        {
            isDead = true;
            displayedHealth = 0.0f;
            RefreshDisplay();
        }

        private void HandleStaminaChanged(float newStamina, float delta)
        {
            displayedStamina = newStamina;
            RefreshDisplay();
        }

        public void RefreshDisplay()
        {
            float safeMaxHealth = Mathf.Max(1.0f, maxHealth);
            float safeMaxStamina = Mathf.Max(1.0f, maxStamina);

            healthPercent = Mathf.Clamp01(displayedHealth / safeMaxHealth);
            staminaPercent = Mathf.Clamp01(displayedStamina / safeMaxStamina);

            if (healthLabel != null)
            {
                healthLabel.text = $"HEALTH: {Mathf.CeilToInt(displayedHealth)} / {Mathf.CeilToInt(maxHealth)}";
            }
            if (healthBar != null)
            {
                healthBar.fillAmount = healthPercent;
            }
            if (staminaLabel != null)
            {
                staminaLabel.text = $"STAMINA: {Mathf.CeilToInt(displayedStamina)} / {Mathf.CeilToInt(maxStamina)}";
            }
            if (staminaBar != null)
            {
                staminaBar.fillAmount = staminaPercent;
            }
        }
    }
}
