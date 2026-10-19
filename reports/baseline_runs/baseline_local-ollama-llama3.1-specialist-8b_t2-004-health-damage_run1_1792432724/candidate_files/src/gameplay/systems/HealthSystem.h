#ifndef HEALTH_SYSTEM_H
#define HEALTH_SYSTEM_H

#include "EntitySystem.h"
#include "HealthComponent.h"

class HealthSystem : public EntitySystem {
public:
    static constexpr float kUpdateInterval = 1.0f / 60.0f; // seconds

    HealthSystem();
    ~HealthSystem() override;

    void Update(Time::Delta delta) override;
};

#endif // HEALTH_SYSTEM_H
