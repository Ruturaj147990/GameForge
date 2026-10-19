using System;
using UnityEngine;

namespace GameForge.Benchmark
{
    /// <summary>
    /// Reference implementation of Health and Damage System for Unity (T2-004).
    /// Conforms to frozen benchmark specifications:
    /// - MaxHealth: 100, InitialHealth: 100, Alive
    /// - Invulnerability Duration: 0.75s
    /// - Exactly-once death event emission
    /// - Clamping, invalid input rejection, and event ordering
    /// </summary>
    public class HealthComponent : MonoBehaviour
    {
        [Header("Configuration")]
        public float maxHealth = 100.0f;
        public float invulnerabilityDuration = 0.75f;

        [Header("Runtime State")]
        [SerializeField] private float currentHealth = 100.0f;
        [SerializeField] private bool isDead = false;

        // Events
        public event Action<float, float> OnHealthChanged;      // newHealth, delta
        public event Action<float, float> OnDamageAccepted;     // damageAmount, remainingHealth
        public event Action OnDeath;

        // Public Accessors
        public float CurrentHealth => currentHealth;
        public float MaxHealth => maxHealth;
        public bool IsDead => isDead;
        public bool IsAlive => !isDead;

        // Timing & Simulation Control
        private float lastAcceptedHitTime = -1000.0f;
        private bool useSimulationTime = false;
        private float currentSimulationTime = 0.0f;
        private bool isProcessingOperation = false;

        private void Awake()
        {
            currentHealth = maxHealth;
            isDead = false;
        }

        public void SetSimulationTimeOverride(bool enable, float initialTime = 0.0f)
        {
            useSimulationTime = enable;
            currentSimulationTime = initialTime;
        }

        public void AdvanceSimulationTime(float deltaSeconds)
        {
            if (!float.IsNaN(deltaSeconds) && !float.IsInfinity(deltaSeconds) && deltaSeconds >= 0.0f)
            {
                currentSimulationTime += deltaSeconds;
            }
        }

        public float GetCurrentGameTime()
        {
            return useSimulationTime ? currentSimulationTime : Time.time;
        }

        public bool IsInvulnerable()
        {
            if (isDead) return false;
            float now = GetCurrentGameTime();
            return (now - lastAcceptedHitTime) < invulnerabilityDuration;
        }

        public bool ApplyDamage(float damageAmount)
        {
            if (isProcessingOperation) return false;
            if (float.IsNaN(damageAmount) || float.IsInfinity(damageAmount) || damageAmount <= 0.0f) return false;
            if (isDead) return false;

            float now = GetCurrentGameTime();
            if ((now - lastAcceptedHitTime) < invulnerabilityDuration)
            {
                return false; // Ignored without extending timer
            }

            isProcessingOperation = true;
            lastAcceptedHitTime = now;

            float oldHealth = currentHealth;
            float newHealth = Mathf.Clamp(oldHealth - damageAmount, 0.0f, maxHealth);
            float delta = newHealth - oldHealth;

            currentHealth = newHealth;

            // 1. Health Changed Notification
            OnHealthChanged?.Invoke(currentHealth, delta);

            // 2. Damage Accepted Notification
            OnDamageAccepted?.Invoke(damageAmount, currentHealth);

            // 3. Single Death Notification
            if (currentHealth <= 0.0f && !isDead)
            {
                isDead = true;
                OnDeath?.Invoke();
            }

            isProcessingOperation = false;
            return true;
        }

        public bool ApplyHealing(float healAmount)
        {
            if (isProcessingOperation) return false;
            if (float.IsNaN(healAmount) || float.IsInfinity(healAmount) || healAmount <= 0.0f) return false;
            if (isDead) return false;
            if (currentHealth >= maxHealth) return false;

            isProcessingOperation = true;

            float oldHealth = currentHealth;
            float newHealth = Mathf.Clamp(oldHealth + healAmount, 0.0f, maxHealth);
            float delta = newHealth - oldHealth;

            if (delta > 0.0f)
            {
                currentHealth = newHealth;
                OnHealthChanged?.Invoke(currentHealth, delta);
                isProcessingOperation = false;
                return true;
            }

            isProcessingOperation = false;
            return false;
        }

        public void ResetComponentState()
        {
            currentHealth = maxHealth;
            isDead = false;
            lastAcceptedHitTime = -1000.0f;
            currentSimulationTime = 0.0f;
            isProcessingOperation = false;
        }
    }
}
