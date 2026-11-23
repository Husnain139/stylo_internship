/*
    Gold runbook

    Run these files in wh_AdventureWorks_Gold in this order:

      1. 01_create_gold_tables.sql       -- once
      2. 02_create_gold_source_views.sql -- once, or after changing Gold logic
      3. 03_create_load_procedure.sql    -- once, or after changing load logic

    Then run this file for every full Gold refresh.
    Run 04_validate_gold.sql afterwards to see the checks.
*/

EXEC dbo.usp_Load_Gold;
GO
