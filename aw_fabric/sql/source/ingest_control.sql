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

    is_core = 1 marks Silver inputs for FactSales and FactStock.
    BusinessEntityAddress, AddressType, and PhoneNumberType are core because
    the person and store dimensions need one address and one phone. They are
    not Gold tables. TransactionHistory and TransactionHistoryArchive feed
    FactStock. UnitMeasure supplies the product size and weight unit names.
    ProductInventory is not core. FactStock does not read it.

    fabric_user is only db_datareader. SQL Server hides alias types from
    that login, so sys.types has no row for Name, Flag, NameStyle, Phone,
    AccountNumber, or OrderNumber. The column is still visible in
    sys.columns, with system_type_id pointing at nvarchar or bit. Joining
    the alias type drops the column. This script joins the system type id
    on the column instead.

    Those aliases cast as:
      Name           nvarchar(50)   a column literally named Name is also
                                    renamed to {Table}Name
      Flag           bit
      NameStyle      bit
      Phone          nvarchar(25)
      AccountNumber  nvarchar(15)
      OrderNumber    nvarchar(25)
    Columns that already use a system type (int, nvarchar, money, datetime,
    uniqueidentifier, decimal) are copied as they are.
    Separate casts, not aliases: time to nvarchar(16), xml to nvarchar(max),
    sysname to nvarchar(128), geography to text plus Srid, hierarchyid to
    text. varbinary, binary, and image columns are left out.
*/
WITH core_table AS (
    SELECT schema_name, table_name
    FROM (VALUES
        (N'Sales',          N'SalesOrderHeader'),
        (N'Sales',          N'SalesOrderDetail'),
        (N'Sales',          N'Customer'),
        (N'Sales',          N'Store'),
        (N'Sales',          N'SalesTerritory'),
        (N'Production',     N'Product'),
        (N'Production',     N'ProductSubcategory'),
        (N'Production',     N'ProductCategory'),
        (N'Production',     N'ProductCostHistory'),
        (N'Production',     N'UnitMeasure'),
        (N'Production',     N'TransactionHistory'),
        (N'Production',     N'TransactionHistoryArchive'),
        (N'Person',         N'Person'),
        (N'Person',         N'EmailAddress'),
        (N'Person',         N'PersonPhone'),
        (N'Person',         N'PhoneNumberType'),
        (N'Person',         N'Address'),
        (N'Person',         N'StateProvince'),
        (N'Person',         N'CountryRegion'),
        (N'Person',         N'BusinessEntityAddress'),
        (N'Person',         N'AddressType')
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
        CAST(CASE
                WHEN ty.is_user_defined = 1 THEN 1
                WHEN ty.user_type_id IS NULL
                     AND sysbt.user_type_id IS NOT NULL
                     AND c.user_type_id <> c.system_type_id THEN 1
                ELSE 0
            END AS bit) AS is_user_defined,
        COALESCE(ty.name, sysbt.name) AS declared_type,
        bt.name AS physical_type,
        CASE
            WHEN c.name = N'Name' THEN OBJECT_NAME(c.object_id) + N'Name'
            ELSE c.name
        END AS output_name
    FROM sys.columns AS c
    LEFT JOIN sys.types AS ty
        ON ty.user_type_id = c.user_type_id
    LEFT JOIN sys.types AS sysbt
        ON sysbt.user_type_id = c.system_type_id
       AND sysbt.is_user_defined = 0
    INNER JOIN sys.types AS bt
        ON bt.is_user_defined = 0
       AND bt.user_type_id = COALESCE(sysbt.user_type_id, c.user_type_id)
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
                WHEN b.is_user_defined = 0
                     AND b.physical_type IN (N'varbinary', N'binary', N'image')
                     AND b.declared_type NOT IN (N'timestamp', N'rowversion')
                    THEN CAST(NULL AS nvarchar(max))
                WHEN b.declared_type = N'geography'
                    THEN QUOTENAME(b.column_name) + N'.STAsText() AS ' + QUOTENAME(b.output_name)
                WHEN b.declared_type = N'hierarchyid'
                    THEN QUOTENAME(b.column_name) + N'.ToString() AS ' + QUOTENAME(b.output_name)
                WHEN b.declared_type = N'xml'
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS nvarchar(max)) AS ' + QUOTENAME(b.output_name)
                WHEN b.declared_type IN (N'timestamp', N'rowversion')
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS varbinary(8)) AS ' + QUOTENAME(b.output_name)
                WHEN b.declared_type = N'sysname'
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS nvarchar(128)) AS ' + QUOTENAME(b.output_name)
                WHEN b.physical_type = N'time'
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS nvarchar(16)) AS ' + QUOTENAME(b.output_name)
                WHEN b.is_user_defined = 1 OR b.column_name <> b.output_name
                    THEN N'CAST(' + QUOTENAME(b.column_name) + N' AS ' + cast_to.cast_type + N') AS ' + QUOTENAME(b.output_name)
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
    N'v4' AS query_build,
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
