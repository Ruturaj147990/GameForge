#include "HealthSystem.h"

HealthSystem::HealthSystem()
    : EntitySystem("HealthSystem") {}

HealthSystem::~HealthSystem() {}

void HealthSystem::Update(Time::Delta delta) {
    for (Entity* entity : GetEntities<HealthComponent>()) {
        entity->GetComponent<HealthComponent>()->Update(delta);
    }
}
