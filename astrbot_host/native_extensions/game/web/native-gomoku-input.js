(() => {
  "use strict";

  // Pointer mechanics stay separate from the room's rules and authoritative state.
  window.CompanionGomokuInput = {
    create({node, getSurface, getSource, canInteract, onSelect, onPreview, onDrop, onCancel, onLift}) {
      let gesture = null;
      const clickGuards = new WeakMap();

      function targetAt(event) {
        const rect = getSurface()?.getBoundingClientRect();
        if (!rect || event.clientX < rect.left || event.clientY < rect.top
            || event.clientX >= rect.left + rect.width || event.clientY >= rect.top + rect.height) return null;
        return {row: Math.floor((event.clientY - rect.top) / rect.height * 15),
          column: Math.floor((event.clientX - rect.left) / rect.width * 15), x: .5, y: .5};
      }

      function suppressClick(element, event) {
        // Keyboard activation must remain available after a pointer gesture.
        return event.detail !== 0 && Date.now() < (clickGuards.get(element) || 0);
      }

      function cleanup() {
        if (!gesture) return null;
        const current = gesture;
        gesture = null;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", finish);
        window.removeEventListener("pointercancel", cancelPointer);
        window.removeEventListener("blur", cancel);
        window.removeEventListener("pagehide", cancel);
        current.ghost?.remove();
        onLift(current.source, false);
        getSurface()?.classList.toggle("pointer-dragging", false);
        try { current.element.releasePointerCapture?.(current.pointerId); } catch (_) { /* Already released. */ }
        onPreview(null);
        return current;
      }

      function cancel(notify = true) {
        const current = cleanup();
        if (!current) return;
        clickGuards.set(current.element, Date.now() + 500);
        if (notify) onCancel("cancelled");
      }

      function cancelPointer(event) {
        if (gesture && event.pointerId === gesture.pointerId) cancel();
      }

      function move(event) {
        if (!gesture || event.pointerId !== gesture.pointerId) return;
        event.preventDefault?.();
        const current = gesture;
        const distance = Math.hypot(event.clientX - current.startX, event.clientY - current.startY);
        if (!current.moved && distance > (current.touch ? 7 : 4)) {
          current.moved = true;
          getSurface().classList.add("pointer-dragging");
          onLift(current.source, true);
          const ghost = node("div", "gomoku-drag-piece");
          ghost.setAttribute("aria-hidden", "true");
          ghost.appendChild(node("span", `stone ${current.source.color === 1 ? "stone-black" : "stone-white"}`));
          getSurface().appendChild(ghost);
          current.ghost = ghost;
        }
        if (current.ghost) {
          const rect = getSurface().getBoundingClientRect();
          // No coordinate clamping or CSS transition: the lifted stone follows the pointer immediately.
          current.ghost.style.left = `${event.clientX - rect.left}px`;
          current.ghost.style.top = `${event.clientY - rect.top - (current.touch ? 32 : 0)}px`;
        }
        onPreview(targetAt(event), {source: current.source, touch: current.touch, dragging: current.moved});
      }

      function finish(event) {
        if (!gesture || event.pointerId !== gesture.pointerId) return;
        const target = targetAt(event);
        const current = cleanup();
        clickGuards.set(current.element, Date.now() + 500);
        if (!current.moved && !current.destination) {
          onSelect(current.source);
        } else if (target) {
          onDrop(target, current.moved ? "drag" : "click", current.source);
        } else onCancel("outside");
      }

      function begin(event, element, source, destination) {
        if (!canInteract() || !source || gesture || event.isPrimary === false
            || (event.button !== undefined && event.button !== 0)) return;
        event.preventDefault();
        event.stopPropagation?.();
        gesture = {element, source, destination, pointerId: event.pointerId,
          startX: event.clientX, startY: event.clientY, touch: event.pointerType === "touch", moved: false};
        try { element.setPointerCapture?.(event.pointerId); } catch (_) { /* Window listeners cover older browsers. */ }
        window.addEventListener("pointermove", move, {passive: false});
        window.addEventListener("pointerup", finish, {passive: false});
        window.addEventListener("pointercancel", cancelPointer);
        window.addEventListener("blur", cancel);
        window.addEventListener("pagehide", cancel);
        if (destination) onPreview(targetAt(event), {source, touch: gesture.touch, dragging: false});
      }

      function bindSource(element, source) {
        element.addEventListener("pointerdown", event => begin(event, element, source, false));
        element.addEventListener("click", event => {
          event.stopPropagation();
          if (!canInteract() || suppressClick(element, event)) return;
          onSelect(source);
        });
      }

      function bindPoint(element, target) {
        element.addEventListener("pointerdown", event => begin(event, element, getSource(), true));
        element.addEventListener("click", event => {
          if (!canInteract() || suppressClick(element, event)) return;
          onDrop(target, "click", getSource());
        });
      }

      function bindSurface(surface) {
        surface.addEventListener("pointermove", event => {
          if (gesture || !canInteract() || event.pointerType === "touch") return;
          const source = getSource();
          onPreview(source ? targetAt(event) : null, {source});
        });
        surface.addEventListener("pointerleave", () => { if (!gesture) onPreview(null); });
      }

      return {bindSource, bindPoint, bindSurface, cancel: () => cancel(false), isActive: () => Boolean(gesture)};
    },
  };
})();
