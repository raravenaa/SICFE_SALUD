from django.db import migrations

FORWARD = """
CREATE FUNCTION sicfe_guard_movement() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'DRAFT' THEN
        RAISE EXCEPTION 'Los movimientos cerrados no se modifican ni eliminan';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sicfe_movement_immutable BEFORE UPDATE OR DELETE ON inventory_movement
FOR EACH ROW EXECUTE FUNCTION sicfe_guard_movement();

CREATE FUNCTION sicfe_guard_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_status varchar;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT status INTO parent_status FROM inventory_movement
        WHERE id = OLD.movement_id FOR UPDATE;
        IF parent_status <> 'DRAFT' THEN
            RAISE EXCEPTION 'Las lineas de movimientos cerrados son inmutables';
        END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        SELECT status INTO parent_status FROM inventory_movement
        WHERE id = NEW.movement_id FOR UPDATE;
        IF parent_status <> 'DRAFT' THEN
            RAISE EXCEPTION 'Solo se agregan lineas a borradores';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER sicfe_line_immutable BEFORE INSERT OR UPDATE OR DELETE ON inventory_movementline
FOR EACH ROW EXECUTE FUNCTION sicfe_guard_line();

CREATE FUNCTION sicfe_deny_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Este registro historico es inmutable';
END $$;
CREATE TRIGGER sicfe_audit_immutable BEFORE UPDATE OR DELETE ON inventory_auditevent
FOR EACH ROW EXECUTE FUNCTION sicfe_deny_history_change();
CREATE TRIGGER sicfe_lot_immutable BEFORE UPDATE OR DELETE ON inventory_lot
FOR EACH ROW EXECUTE FUNCTION sicfe_deny_history_change();

CREATE FUNCTION sicfe_guard_product_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.code <> NEW.code OR OLD.unit <> NEW.unit) AND EXISTS (
        SELECT 1 FROM inventory_movementline ml JOIN inventory_lot l ON l.id = ml.lot_id
        WHERE l.product_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'No se cambia codigo ni unidad de productos con movimientos';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sicfe_product_identity BEFORE UPDATE ON inventory_product
FOR EACH ROW EXECUTE FUNCTION sicfe_guard_product_identity();
"""

REVERSE = """
DROP TRIGGER sicfe_product_identity ON inventory_product;
DROP FUNCTION sicfe_guard_product_identity();
DROP TRIGGER sicfe_lot_immutable ON inventory_lot;
DROP TRIGGER sicfe_audit_immutable ON inventory_auditevent;
DROP FUNCTION sicfe_deny_history_change();
DROP TRIGGER sicfe_line_immutable ON inventory_movementline;
DROP FUNCTION sicfe_guard_line();
DROP TRIGGER sicfe_movement_immutable ON inventory_movement;
DROP FUNCTION sicfe_guard_movement();
"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_alter_movement_confirmed_by")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
