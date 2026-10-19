#include "HealthSystem.h"
#include "HealthComponent.h"

namespace game {

void HealthSystem::update(float deltaTime) {
    for (auto entity : getEntities()) {
        auto& health = getComponent<Health>(entity);
        health.update(deltaTime);

        if (health.isDead()) {
            // Emit death event
            emitEvent(entity, "death");
        }
    }
}

} // namespace game
