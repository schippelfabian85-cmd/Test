-- Row Level Security für PostgreSQL 16 (Kernel §2: Mandantentrennung).
--
-- Die Anwendung filtert jede Abfrage zusätzlich anwendungsseitig über
-- tenant_id; RLS ist die zweite Verteidigungslinie. Einspielen nach dem
-- Schemaaufbau; die Anwendung setzt je Verbindung:
--     SET app.tenant_id = '<uuid des mandanten>';

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'tenant_id' AND table_schema = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I
             USING (tenant_id = current_setting(''app.tenant_id'')::text)
             WITH CHECK (tenant_id = current_setting(''app.tenant_id'')::text)', t);
    END LOOP;
END $$;

-- Tabellen ohne tenant_id (rolle, mindestlohn) sind bewusst global.
