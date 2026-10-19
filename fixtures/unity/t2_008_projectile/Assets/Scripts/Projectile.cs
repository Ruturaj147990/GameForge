using System;
using UnityEngine;

namespace GameForge.Benchmark
{
    /// <summary>
    /// Reference implementation of Projectile Actor/Component for Unity (T2-008).
    /// Conforms to frozen benchmark specifications:
    /// - Speed: 2000 cm/s (20 m/s), Damage: 20.0, Lifespan: 5.0s
    /// - Owner exclusion (owner cannot be damaged by own projectile)
    /// - Exactly-once damage application on valid collision
    /// - Collision disabling & cleanup upon impact
    /// - Lifetime cleanup when no collision occurs
    /// </summary>
    public class Projectile : MonoBehaviour
    {
        [Header("Configuration")]
        public float speed = 20.0f; // 20 m/s in Unity units (2000 cm/s)
        public float damageAmount = 20.0f;
        public float lifespan = 5.0f;

        [Header("Runtime State")]
        [SerializeField] private GameObject ownerObject;
        [SerializeField] private bool hasImpacted = false;
        [SerializeField] private int damageAppliedCount = 0;

        private Rigidbody rb;
        private Collider col;
        private float spawnTime;

        public float Speed => speed;
        public float DamageAmount => damageAmount;
        public float Lifespan => lifespan;
        public GameObject OwnerObject => ownerObject;
        public bool HasImpacted => hasImpacted;
        public int DamageAppliedCount => damageAppliedCount;

        private void Awake()
        {
            rb = GetComponent<Rigidbody>();
            col = GetComponent<Collider>();
            spawnTime = Time.time;
        }

        private void Start()
        {
            if (rb != null)
            {
                rb.linearVelocity = transform.forward * speed;
            }
            Destroy(gameObject, lifespan);
        }

        public void Initialize(GameObject owner, Vector3 direction, float damage = 20.0f, float projSpeed = 20.0f)
        {
            ownerObject = owner;
            damageAmount = damage;
            speed = projSpeed;
            transform.forward = direction.normalized;

            if (rb != null)
            {
                rb.linearVelocity = transform.forward * speed;
            }
        }

        private void OnCollisionEnter(Collision collision)
        {
            HandleHit(collision.gameObject);
        }

        private void OnTriggerEnter(Collider other)
        {
            HandleHit(other.gameObject);
        }

        public bool HandleHit(GameObject hitObject)
        {
            if (hasImpacted)
            {
                return false;
            }

            // Exclude owner
            if (ownerObject != null && hitObject == ownerObject)
            {
                return false;
            }

            hasImpacted = true;

            // Disable further collision
            if (col != null)
            {
                col.enabled = false;
            }

            // Check damage validity
            if (float.IsNaN(damageAmount) || float.IsInfinity(damageAmount) || damageAmount <= 0.0f)
            {
                Destroy(gameObject);
                return false;
            }

            if (hitObject != null)
            {
                var healthComp = hitObject.GetComponent<HealthComponent>();
                if (healthComp != null && healthComp.IsAlive)
                {
                    bool applied = healthComp.ApplyDamage(damageAmount);
                    if (applied)
                    {
                        damageAppliedCount++;
                    }
                }
            }

            Destroy(gameObject);
            return true;
        }
    }
}
