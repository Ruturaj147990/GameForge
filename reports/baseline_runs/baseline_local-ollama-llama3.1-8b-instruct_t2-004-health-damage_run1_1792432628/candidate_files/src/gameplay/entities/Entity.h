#ifndef ENTITY_H
#define ENTITY_H

#include "entt.hpp"

namespace game {

class Entity : public entt::entity {
public:
    template <typename T>
    T& getComponent() {
        return entt::get<T>(this);
    }

    void emitEvent(entt::id_type entity, const std::string& event) {
        // Emit event to listeners
    }
};

} // namespace game

#endif // ENTITY_H
