using System;
using UnityEngine;

namespace GameForge.Benchmark
{
    /// <summary>
    /// Reference implementation of Third-Person Player Controller for Unity (T2-001).
    /// Conforms to frozen benchmark specifications.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public class PlayerController : MonoBehaviour
    {
        [Header("Kinematics (Target: 6.0 m/s, Accel: 40 m/s^2, Decel: 55 m/s^2)")]
        public float maxRunSpeed = 6.0f;
        public float acceleration = 40.0f;
        public float deceleration = 55.0f;
        public float slopeLimit = 45.0f;
        public float stepOffset = 0.35f;

        [Header("Jumping & Timing (Apex: 1.2m, Coyote: 0.10s, Buffer: 0.12s)")]
        public float jumpApexHeight = 1.2f;
        public float gravity = 9.81f;
        public float coyoteTimeWindow = 0.10f;
        public float jumpBufferWindow = 0.12f;

        private CharacterController characterController;
        private Vector3 currentVelocity = Vector3.zero;
        private float verticalVelocity = 0.0f;
        private float coyoteTimeCounter = 0.0f;
        private float jumpBufferCounter = 0.0f;

        private void Awake()
        {
            characterController = GetComponent<CharacterController>();
            characterController.radius = 0.35f;
            characterController.height = 1.8f;
            characterController.slopeLimit = slopeLimit;
            characterController.stepOffset = stepOffset;
        }

        private void Update()
        {
            HandleGroundAndJumping();
            HandleHorizontalMovement();
        }

        private void HandleGroundAndJumping()
        {
            bool isGrounded = characterController.isGrounded;

            if (isGrounded)
            {
                coyoteTimeCounter = coyoteTimeWindow;
                if (verticalVelocity < 0.0f)
                {
                    verticalVelocity = -2.0f; // Stable ground sticking
                }
            }
            else
            {
                coyoteTimeCounter -= Time.deltaTime;
                verticalVelocity -= gravity * Time.deltaTime;
            }

            if (Input.GetButtonDown("Jump"))
            {
                jumpBufferCounter = jumpBufferWindow;
            }
            else
            {
                jumpBufferCounter -= Time.deltaTime;
            }

            // Execute jump if buffered and coyote window is open
            if (jumpBufferCounter > 0.0f && coyoteTimeCounter > 0.0f)
            {
                // v = sqrt(2 * g * h)
                verticalVelocity = Mathf.Sqrt(2.0f * gravity * jumpApexHeight);
                jumpBufferCounter = 0.0f;
                coyoteTimeCounter = 0.0f;
            }
        }

        private void HandleHorizontalMovement()
        {
            float horizontal = Input.GetAxisRaw("Horizontal");
            float vertical = Input.GetAxisRaw("Vertical");
            Vector3 inputDirection = new Vector3(horizontal, 0.0f, vertical).normalized;

            Vector3 targetVelocity = inputDirection * maxRunSpeed;
            float rate = inputDirection.sqrMagnitude > 0.001f ? acceleration : deceleration;

            currentVelocity = Vector3.MoveTowards(currentVelocity, targetVelocity, rate * Time.deltaTime);
            Vector3 movement = currentVelocity + Vector3.up * verticalVelocity;
            characterController.Move(movement * Time.deltaTime);
        }
    }
}
