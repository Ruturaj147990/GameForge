#ifndef HEALTH_COMPONENT_H
#define HEALTH_COMPONENT_H

#include "entt.hpp"
#include "components/Component.h"

namespace game {

struct Health {
    float maxHealth = 100.0f;
    float currentHealth = 100.0f;
    float invulnerabilityWindowDuration = 2.0f; // seconds
    float invulnerabilityWindowTimer = 0.0f;

    void onDamage(float damage) {
        if (invulnerabilityWindowTimer > 0.0f) {
            return;
        }

        currentHealth -= damage;
        invulnerabilityWindowTimer = invulnerabilityWindowDuration;

        // Clamp health to max allowed range
        currentHealth = std::max(0.0f, std::min(currentHealth, maxHealth));
    }

    void update(float deltaTime) {
        if (invulnerabilityWindowTimer > 0.0f) {
            invulnerabilityWindowTimer -= deltaTime;
        }
    }

    bool isDead() const {
        return currentHealth <= 0.0f;
    }
};

class HealthComponent : public Component<Health> {
public:
    static constexpr auto tag = "health";
};

} // namespace game

#endif // HEALTH_COMPONENT_H
