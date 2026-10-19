#include "HealthComponent.h"

HealthComponent::HealthComponent(Entity* entity)
    : EntityComponent(entity), m_health(kMaxHealth) {}

HealthComponent::~HealthComponent() {}

void HealthComponent::TakeDamage(float damage) {
    if (m_invulnerabilityWindowActive) return;

    float newHealth = std::max(m_minHealth, m_health - damage);
    m_health = newHealth;
    if (newHealth <= 0.0f) {
        // Death event
        EmitEvent("Death");
        m_invulnerabilityWindowStart = Time::GetTime() + kInvulnerabilityWindowDuration;
        m_invulnerabilityWindowActive = true;
    }
}

void HealthComponent::Update(Time::Delta delta) {
    if (m_invulnerabilityWindowActive && Time::GetTime() >= m_invulnerabilityWindowStart) {
        m_invulnerabilityWindowActive = false;
    }
}
