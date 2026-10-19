using System;
using UnityEngine;

namespace GameForge.Benchmark
{
    public class StaminaComponent : MonoBehaviour
    {
        [Header("Configuration")]
        public float maxStamina = 100.0f;

        [Header("Runtime State")]
        [SerializeField] private float currentStamina = 100.0f;

        public event Action<float, float> OnStaminaChanged; // newStamina, delta

        public float CurrentStamina => currentStamina;
        public float MaxStamina => maxStamina;

        private bool isProcessingOperation = false;

        private void Awake()
        {
            currentStamina = maxStamina;
        }

        public void SetCurrentStamina(float newStamina)
        {
            if (!float.IsNaN(newStamina) && !float.IsInfinity(newStamina))
            {
                currentStamina = Mathf.Clamp(newStamina, 0.0f, maxStamina);
            }
        }

        public bool ApplyStaminaRestoration(float amount)
        {
            if (isProcessingOperation) return false;
            if (float.IsNaN(amount) || float.IsInfinity(amount) || amount <= 0.0f) return false;
            if (currentStamina >= maxStamina) return false;

            isProcessingOperation = true;

            float oldStamina = currentStamina;
            float newStamina = Mathf.Clamp(oldStamina + amount, 0.0f, maxStamina);
            float delta = newStamina - oldStamina;

            if (delta > 0.0f)
            {
                currentStamina = newStamina;
                OnStaminaChanged?.Invoke(currentStamina, delta);
                isProcessingOperation = false;
                return true;
            }

            isProcessingOperation = false;
            return false;
        }

        public void ResetComponentState()
        {
            currentStamina = maxStamina;
            isProcessingOperation = false;
        }
    }
}
