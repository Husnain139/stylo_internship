/* Run after load_gold.sql. Every result is read-only. */

/* Row counts. */
SELECT N'FactSales' AS CheckName, COUNT(*) AS RowsFound FROM dbo.FactSales
UNION ALL SELECT N'DimCustomer', COUNT(*) FROM dbo.DimCustomer
UNION ALL SELECT N'DimStore', COUNT(*) FROM dbo.DimStore
UNION ALL SELECT N'DimProduct', COUNT(*) FROM dbo.DimProduct
UNION ALL SELECT N'DimDate', COUNT(*) FROM dbo.DimDate
UNION ALL SELECT N'FactStock', COUNT(*) FROM dbo.FactStock;

/* Allocated line tax and freight must add back to the order header totals. */
SELECT
    COUNT(*) AS OrdersChecked,
    SUM(CASE WHEN ABS(header.TaxAmt - fact.AllocatedTaxAmount) > 0 THEN 1 ELSE 0 END) AS OrdersTaxOff,
    SUM(CASE WHEN ABS(header.Freight - fact.AllocatedFreightAmount) > 0 THEN 1 ELSE 0 END) AS OrdersFreightOff
FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderHeader] AS header
INNER JOIN (
    SELECT
        OrderID,
        SUM(AllocatedTaxAmount) AS AllocatedTaxAmount,
        SUM(AllocatedFreightAmount) AS AllocatedFreightAmount
    FROM dbo.FactSales
    GROUP BY OrderID
) AS fact
    ON fact.OrderID = header.SalesOrderID;

/* Each product's first stock day must start at zero. */
SELECT
    SUM(CASE WHEN ranked.RowNumber = 1 AND ranked.OpeningQty <> 0 THEN 1 ELSE 0 END)
        AS ProductsWhoseFirstDayIsNotZero
FROM (
    SELECT
        ProductKey,
        OpeningQty,
        ROW_NUMBER() OVER (PARTITION BY ProductKey ORDER BY DateKey) AS RowNumber
    FROM dbo.FactStock
) AS ranked;

/* A successful load adds no new error row. */
SELECT COUNT(*) AS EtlLogRows FROM dbo.ETL_Log;
