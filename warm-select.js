(() => {
    function buildWarmSelect(select) {
        if (select.dataset.warmSelectReady === "true") return;
        select.dataset.warmSelectReady = "true";
        select.classList.add("warm-select-native");

        const wrapper = document.createElement("div");
        wrapper.className = "warm-select";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "warm-select-button";
        button.setAttribute("aria-haspopup", "listbox");
        button.setAttribute("aria-expanded", "false");

        const menu = document.createElement("ul");
        menu.className = "warm-select-menu";
        menu.setAttribute("role", "listbox");
        menu.hidden = true;

        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        wrapper.appendChild(button);
        wrapper.appendChild(menu);

        let focusedIndex = -1;

        function sync() {
            const selectedOption = select.options[select.selectedIndex] || select.options[0];
            button.textContent = selectedOption ? selectedOption.textContent : "请选择";
            [...menu.children].forEach((item, index) => {
                const isSelected = index === select.selectedIndex;
                item.classList.toggle("selected", isSelected);
                item.setAttribute("aria-selected", String(isSelected));
            });
        }

        function closeMenu() {
            wrapper.classList.remove("open");
            menu.hidden = true;
            button.setAttribute("aria-expanded", "false");
            focusedIndex = -1;
            [...menu.children].forEach(item => item.classList.remove("focused"));
        }

        function openMenu() {
            document.querySelectorAll(".warm-select.open").forEach(other => {
                if (other !== wrapper) {
                    other.classList.remove("open");
                    const otherMenu = other.querySelector(".warm-select-menu");
                    const otherButton = other.querySelector(".warm-select-button");
                    if (otherMenu) otherMenu.hidden = true;
                    if (otherButton) otherButton.setAttribute("aria-expanded", "false");
                }
            });
            wrapper.classList.add("open");
            menu.hidden = false;
            button.setAttribute("aria-expanded", "true");
            focusedIndex = Math.max(0, select.selectedIndex);
            focusOption(focusedIndex);
        }

        function focusOption(index) {
            const items = [...menu.children];
            if (!items.length) return;
            focusedIndex = (index + items.length) % items.length;
            items.forEach((item, i) => item.classList.toggle("focused", i === focusedIndex));
            items[focusedIndex].scrollIntoView({ block: "nearest" });
        }

        [...select.options].forEach((option, index) => {
            const item = document.createElement("li");
            item.className = "warm-select-option";
            item.setAttribute("role", "option");
            item.textContent = option.textContent;
            item.addEventListener("click", () => {
                if (option.disabled) return;
                select.selectedIndex = index;
                select.dispatchEvent(new Event("change", { bubbles: true }));
                sync();
                closeMenu();
                button.focus();
            });
            menu.appendChild(item);
        });

        button.addEventListener("click", () => {
            menu.hidden ? openMenu() : closeMenu();
        });

        button.addEventListener("keydown", event => {
            if (["ArrowDown", "ArrowUp", "Home", "End", "Enter", " ", "Escape"].includes(event.key)) {
                event.preventDefault();
            }
            if (event.key === "Escape") return closeMenu();
            if (menu.hidden) openMenu();
            if (event.key === "ArrowDown") focusOption(focusedIndex + 1);
            if (event.key === "ArrowUp") focusOption(focusedIndex - 1);
            if (event.key === "Home") focusOption(0);
            if (event.key === "End") focusOption(menu.children.length - 1);
            if ((event.key === "Enter" || event.key === " ") && focusedIndex >= 0) {
                menu.children[focusedIndex].click();
            }
        });

        select.addEventListener("change", sync);
        document.addEventListener("click", event => {
            if (!wrapper.contains(event.target)) closeMenu();
        });

        sync();
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("select").forEach(buildWarmSelect);
    });
})();
