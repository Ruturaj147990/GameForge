using UnityEngine;

namespace GameForge.Benchmark
{
    /// <summary>
    /// Reference implementation of Third-Person Follow/Orbit Camera for Unity (T2-001).
    /// Prevents intersection with blocking world geometry and maintains minimum clearance.
    /// </summary>
    public class ThirdPersonCamera : MonoBehaviour
    {
        [Header("Target & Distance (Target Arm Length: 4.0m)")]
        public Transform target;
        public float targetArmLength = 4.0f;
        public float minClearance = 0.1f;
        public LayerMask collisionMask;

        [Header("Orbit / Look Controls")]
        public float mouseSensitivity = 2.0f;
        public float pitchMin = -30.0f;
        public float pitchMax = 70.0f;

        private float yaw = 0.0f;
        private float pitch = 15.0f;

        private void LateUpdate()
        {
            if (target == null) return;

            // Handle look input
            yaw += Input.GetAxis("Mouse X") * mouseSensitivity;
            pitch -= Input.GetAxis("Mouse Y") * mouseSensitivity;
            pitch = Mathf.Clamp(pitch, pitchMin, pitchMax);

            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0.0f);
            Vector3 desiredPosition = target.position - (rotation * Vector3.forward * targetArmLength);

            // Sphere cast / raycast for camera wall collision
            Vector3 direction = desiredPosition - target.position;
            float maxDistance = direction.magnitude;

            RaycastHit hit;
            if (Physics.SphereCast(target.position, minClearance, direction.normalized, out hit, maxDistance, collisionMask))
            {
                // Constrain camera position in front of obstacle
                transform.position = target.position + direction.normalized * Mathf.Max(hit.distance - minClearance, 0.2f);
            }
            else
            {
                transform.position = desiredPosition;
            }

            transform.LookAt(target.position + Vector3.up * 1.2f);
        }
    }
}
