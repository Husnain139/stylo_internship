/*
    Read-only control query for pl_AdventureWorks_Medallion.

    Run it with a Lookup activity against AdventureWorks2025 through the
    gateway. It creates nothing in the source database. fabric_user needs
    only db_datareader.

    One row per base table that Bronze copies. source_query is the Copy
    source. The pipeline appends the ModifiedDate predicate itself when
    RunMode is Incremental. This query does not embed a watermark value.

    Excluded: the cdc schema, dbo.AWBuildVersion, dbo.sysdiagrams,
    dbo.systranschemas, and Person.Password.

    is_core = 1 marks Silver inputs. BusinessEntityAddress, AddressType,
    PhoneNumberType, SalesReason, and SpecialOfferProduct are core because
    Gold cannot resolve geography, phone, sales reason, or the detail-to-offer
    foreign key without them. They are not Gold tables.
*/
WITH core_table AS (
    SELECT schema_name, table_name
    FROM (VALUES
        (N'Sales',          N'SalesOrderHeader'),
        (N'Sales',          N'SalesOrderDetail'),
        (N'Sales',          N'SalesOrderHeaderSalesReason'),
        (N'Sales',          N'SalesReason'),
        (N'Sales',          N'Customer'),
        (N'Sales',          N'Store'),
        (N'Sales',          N'SpecialOffer'),
        (N'Sales',          N'SpecialOfferProduct'),
        (N'Sales',          N'Currency'),
        (N'Sales',          N'CurrencyRate'),
        (N'Sales',          N'SalesTerritory'),
        (N'Sales',          N'SalesPerson'),
        (N'Sales',          N'SalesPersonQuotaHistory'),
        (N'Production',     N'Product'),
        (N'Production',     N'ProductSubcategory'),
        (N'Production',     N'ProductCategory'),
        (N'Production',     N'ProductCostHistory'),
        (N'Person',         N'Person'),
        (N'Person',         N'EmailAddress'),
        (N'Person',         N'PersonPhone'),
        (N'Person',         N'PhoneNumberType'),
        (N'Person',         N'Address'),
        (N'Person',         N'StateProvince'),
        (N'Person',         N'CountryRegion'),
        (N'Person',         N'BusinessEntityAddress'),
        (N'Person',         N'AddressType'),
        (N'Purchasing',     N'ShipMethod'),
        (N'HumanResources', N'Employee')
    ) AS v(schema_name, table_name)
),
base_type AS (
    SELECT
        c.object_id,
        c.column_id,
        c.name AS column_name,
        c.max_length,
        c.precision,
        c.scale,
        c.is_computed,
        ty.name AS declared_type,
        bt.name AS physical_type
    FROM sys.columns AS c
    INNER JOIN sys.types AS ty
        ON ty.user_type_id = c.user_type_id
    INNER JOIN sys.types AS bt
        ON bt.user_type_id = CASE
               WHEN ty.is_user_defined = 1 THEN ty.system_type_id
               ELSE ty.user_type_id
           END
       AND bt.is_user_defined = 0
    WHERE c.is_hidden = 0
),
projected AS (
    SELECT
        b.object_id,
        b.column_id,
        part.part_no,
        part.expr
    FROM base_type AS b
    CROSS APPLY (
        SELECT
            CASE
                WHEN b.physical_type IN (N'varchar', N'char', N'binary')
                    THEN b.physical_type
                         + CASE
                               WHEN b.max_length = -1 THEN N'(max)'
                               ELSE N'(' + CAST(b.max_length AS nvarchar(10)) + N')'
                           END
                WHEN b.physical_type IN (N'nvarchar', N'nchar')
                    THEN b.physical_type
                         + CASE
                               WHEN b.max_length = -1 THEN N'(max)'
                               ELSE N'(' + CAST(b.max_length / 2 AS nvarchar(10)) + N')'
                           END
                WHEN b.physical_type IN (N'decimal', N'numeric')
                    THEN b.physical_type + N'('
                         + CAST(b.precision AS nvarchar(10)) + N','
                         + CAST(b.scale AS nvarchar(10)) + N')'
                WHEN b.physical_type IN (N'datetime2', N'datetimeoffset', N'time')
                    THEN b.physical_type + N'(' + CAST(b.scale AS nvarchar(10)) + N')'
                ELSE b.physical_type
            END AS cast_type
    ) AS cast_to
    CROSS APPLY (
        SELECT
            CAST(1 AS int) AS part_no,
            CASE
                WHEN b.physical_type IN (N'varbinary', N'binary', N'image')
                     AND b.declared_type NOT IN (N'timestamp', N'rowversion')
                    THEN CAST(NULL AS nvarchar(max))
                WHEN b.declared_type = N'geography'
                    THEN QUOTENAME(b.column_name) + N'.STAsText() AS ' + QUOTENAME(b.column_name)
                WHEN b.declared_type = N'hierarchyid'
                    THEN QUOTENAME(b.column_name) + N'.ToString() AS ' + QUOTENAME(b.column_name)
                WHEN b.declared_type = N'xml'
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS nvarchar(max)) AS ' + QUOTENAME(b.column_name)
                WHEN b.declared_type IN (N'timestamp', N'rowversion')
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS varbinary(8)) AS ' + QUOTENAME(b.column_name)
                WHEN b.declared_type = N'sysname'
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS nvarchar(128)) AS ' + QUOTENAME(b.column_name)
                WHEN b.declared_type <> b.physical_type AND b.is_computed = 0
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS ' + cast_to.cast_type + N') AS ' + QUOTENAME(b.column_name)
                ELSE QUOTENAME(b.column_name)
            END AS expr
        UNION ALL
        SELECT
            CAST(2 AS int),
            QUOTENAME(b.column_name) + N'.STSrid AS ' + QUOTENAME(b.column_name + N'Srid')
        WHERE b.declared_type = N'geography'
    ) AS part
    WHERE part.expr IS NOT NULL
),
column_list AS (
    SELECT
        p.object_id,
        STRING_AGG(CAST(p.expr AS nvarchar(max)), N', ')
            WITHIN GROUP (ORDER BY p.column_id, p.part_no) AS select_list
    FROM projected AS p
    GROUP BY p.object_id
),
primary_key AS (
    SELECT
        ic.object_id,
        STRING_AGG(CAST(c.name AS nvarchar(max)), N',')
            WITHIN GROUP (ORDER BY ic.key_ordinal) AS key_columns
    FROM sys.indexes AS i
    INNER JOIN sys.index_columns AS ic
        ON ic.object_id = i.object_id
       AND ic.index_id = i.index_id
    INNER JOIN sys.columns AS c
        ON c.object_id = ic.object_id
       AND c.column_id = ic.column_id
    WHERE i.is_primary_key = 1
    GROUP BY ic.object_id
)
SELECT
    s.name AS source_schema,
    t.name AS source_table,
    s.name AS dest_schema,
    t.name AS dest_table,
    CAST(CASE WHEN core.table_name IS NOT NULL THEN 1 ELSE 0 END AS bit) AS is_core,
    CASE
        WHEN s.name = N'Sales' AND t.name IN (N'SalesOrderHeader', N'SalesOrderDetail')
            THEN N'WATERMARK'
        ELSE N'FULL'
    END AS load_strategy,
    CASE
        WHEN s.name = N'Sales' AND t.name IN (N'SalesOrderHeader', N'SalesOrderDetail')
            THEN N'ModifiedDate'
        ELSE CAST(NULL AS nvarchar(128))
    END AS watermark_column,
    pk.key_columns,
    N'SELECT ' + cols.select_list
        + N' FROM ' + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) AS source_query
FROM sys.tables AS t
INNER JOIN sys.schemas AS s
    ON s.schema_id = t.schema_id
INNER JOIN column_list AS cols
    ON cols.object_id = t.object_id
LEFT JOIN primary_key AS pk
    ON pk.object_id = t.object_id
LEFT JOIN core_table AS core
    ON core.schema_name = s.name
   AND core.table_name = t.name
WHERE t.is_ms_shipped = 0
  AND s.name <> N'cdc'
  AND NOT (
        s.name = N'dbo'
        AND t.name IN (N'AWBuildVersion', N'sysdiagrams', N'systranschemas')
      )
  AND NOT (s.name = N'Person' AND t.name = N'Password')
ORDER BY s.name, t.name;
