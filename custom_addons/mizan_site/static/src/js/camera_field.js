/**
 * An image field whose button opens the phone's rear camera directly.
 *
 * Odoo's own image field opens a file chooser, which on a phone means a menu —
 * camera, photo library, files — before the camera. An engineer photographing
 * a receipt in a builders' merchant wants the camera, so this asks the browser
 * for it with capture="environment". On a desktop the attribute is ignored and
 * the ordinary file picker opens, so the same form works in the office.
 *
 * The photograph is shown back at full width before saving: a blurred receipt
 * caught here costs a second attempt, caught in the office it costs a trip.
 */
import { Component, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class MizanCameraField extends Component {
    static template = "mizan_site.CameraField";
    static props = { ...standardFieldProps };

    setup() {
        this.input = useRef("input");
        this.notification = useService("notification");
        this.state = useState({ busy: false });
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get src() {
        const value = this.value;
        if (!value) {
            return false;
        }
        // A freshly captured photo is held as base64 until the record saves.
        return value.startsWith("data:") ? value : `data:image/jpeg;base64,${value}`;
    }

    open() {
        this.input.el.click();
    }

    async onChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (!file.type.startsWith("image/")) {
            this.notification.add(_t("That is not a photograph."), { type: "danger" });
            return;
        }
        this.state.busy = true;
        try {
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            await this.props.record.update({ [this.props.name]: base64 });
        } finally {
            this.state.busy = false;
        }
    }

    clear() {
        this.props.record.update({ [this.props.name]: false });
    }
}

registry.category("fields").add("mizan_camera", {
    component: MizanCameraField,
    supportedTypes: ["binary"],
});
