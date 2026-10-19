#include "Entity.h"

Entity::Entity()
    : m_componentManager(new ComponentManager()) {}

Entity::~Entity() {
    delete m_componentManager;
}
