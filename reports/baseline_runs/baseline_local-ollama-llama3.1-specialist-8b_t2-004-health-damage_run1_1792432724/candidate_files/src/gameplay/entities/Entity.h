#ifndef ENTITY_H
#define ENTITY_H

#include "ComponentManager.h"

class Entity {
public:
    Entity();
    ~Entity();

    template <typename T>
    T* GetComponent() { return m_componentManager->GetComponent<T>(); }

private:
    ComponentManager* m_componentManager;
};

#endif // ENTITY_H
