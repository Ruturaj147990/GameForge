#ifndef HEALTH_SYSTEM_H
#define HEALTH_SYSTEM_H

#include "entt.hpp"
#include "systems/System.h"

namespace game {

class HealthSystem : public System<HealthComponent> {
public:
    void update(float deltaTime) override;
};

} // namespace game

#endif // HEALTH_SYSTEM_H
