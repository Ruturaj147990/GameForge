#ifndef HEALTH_COMPONENT_H
#define HEALTH_COMPONENT_H

#include "EntityComponent.h"
#include "Time.h"

class HealthComponent : public EntityComponent {
public:
    static constexpr float kInvulnerabilityWindowDuration = 1.0f; // seconds
    static constexpr float kMaxHealth = 100.0f;
    static constexpr float kMinHealth = 0.0f;

    HealthComponent(Entity* entity);
    ~HealthComponent() override;

    void TakeDamage(float damage) override;
    void Update(Time::Delta delta) override;

    float GetHealth() const { return m_health; }
    bool IsInvulnerable() const { return m_invulnerabilityWindowActive; }

private:
    float m_health;
    Time m_invulnerabilityWindowStart;
    bool m_invulnerabilityWindowActive;
};

#endif // HEALTH_COMPONENT_H
