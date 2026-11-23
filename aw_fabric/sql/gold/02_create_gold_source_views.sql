/*
    Run after 01_create_gold_tables.sql.

    These views do not store data. They explain how each fact is calculated.
    The procedure in 03_create_load_procedure.sql simply inserts their rows.
*/

/*
    One output row per SalesOrderDetail.
    Tax and Freight are allocated by each line's share of the header SubTotal.
*/
CREATE OR ALTER VIEW dbo.vw_FactSales_Source
AS
WITH SalesLines AS (
    SELECT
        detail.SalesOrderID AS OrderID,
        detail.SalesOrderDetailID AS OrderLineID,
        date_dimension.DateKey AS SaleDateKey,
        COALESCE(dim_customer.CustomerKey, -1) AS CustomerKey,
        COALESCE(dim_store.StoreKey, -1) AS StoreKey,
        COALESCE(dim_product.ProductKey, -1) AS ProductKey,
        detail.OrderQty AS Qty,
        CAST(detail.UnitPrice AS decimal(19, 4)) AS UnitPrice,
        CAST(COALESCE(detail.UnitPriceDiscount, 0) AS decimal(19, 4)) AS UnitPriceDiscount,
        CAST(detail.UnitPrice * detail.OrderQty AS decimal(19, 4)) AS GrossSalesAmount,
        CAST(detail.UnitPrice * detail.OrderQty * COALESCE(detail.UnitPriceDiscount, 0) AS decimal(19, 4)) AS DiscountAmount,
        CAST(detail.UnitPrice * detail.OrderQty * (1 - COALESCE(detail.UnitPriceDiscount, 0)) AS decimal(19, 4)) AS LineNetSalesAmount,
        header.SubTotal,
        header.TaxAmt,
        header.Freight,
        COALESCE(cost.StandardCost, product.StandardCost, CAST(0 AS decimal(19, 4))) AS UnitStandardCost,
        ROW_NUMBER() OVER (
            PARTITION BY detail.SalesOrderID
            ORDER BY detail.SalesOrderDetailID
        ) AS LineRank
    FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderDetail] AS detail
    INNER JOIN [lh_AdventureWorks_Silver].[cleansed].[SalesOrderHeader] AS header
        ON header.SalesOrderID = detail.SalesOrderID
    INNER JOIN [lh_AdventureWorks_Silver].[cleansed].[Customer] AS customer
        ON customer.CustomerID = header.CustomerID
    INNER JOIN dbo.DimDate AS date_dimension
        ON date_dimension.FullDate = CAST(header.OrderDate AS date)
    LEFT JOIN dbo.DimCustomer AS dim_customer
        ON dim_customer.CustomerID = customer.CustomerID
    LEFT JOIN dbo.DimStore AS dim_store
        ON dim_store.StoreID = customer.StoreID
    LEFT JOIN dbo.DimProduct AS dim_product
        ON dim_product.ProductID = detail.ProductID
    LEFT JOIN [lh_AdventureWorks_Silver].[cleansed].[Product] AS product
        ON product.ProductID = detail.ProductID
    OUTER APPLY (
        SELECT TOP (1) history.StandardCost
        FROM [lh_AdventureWorks_Silver].[cleansed].[ProductCostHistory] AS history
        WHERE history.ProductID = detail.ProductID
          AND history.StartDate <= CAST(header.OrderDate AS date)
          AND (history.EndDate IS NULL OR history.EndDate > CAST(header.OrderDate AS date))
        ORDER BY history.StartDate DESC
    ) AS cost
),
RawAllocation AS (
    SELECT
        SalesLines.*,
        CAST(CASE
            WHEN SubTotal = 0 AND LineRank = 1 THEN TaxAmt
            WHEN SubTotal = 0 THEN 0
            ELSE TaxAmt * LineNetSalesAmount / SubTotal
        END AS decimal(19, 4)) AS TaxRaw,
        CAST(CASE
            WHEN SubTotal = 0 AND LineRank = 1 THEN Freight
            WHEN SubTotal = 0 THEN 0
            ELSE Freight * LineNetSalesAmount / SubTotal
        END AS decimal(19, 4)) AS FreightRaw
    FROM SalesLines
),
AllocatedAmounts AS (
    SELECT
        RawAllocation.*,
        CAST(TaxRaw + CASE
            WHEN LineRank = 1 THEN TaxAmt - SUM(TaxRaw) OVER (PARTITION BY OrderID)
            ELSE 0
        END AS decimal(19, 4)) AS AllocatedTaxAmount,
        CAST(FreightRaw + CASE
            WHEN LineRank = 1 THEN Freight - SUM(FreightRaw) OVER (PARTITION BY OrderID)
            ELSE 0
        END AS decimal(19, 4)) AS AllocatedFreightAmount
    FROM RawAllocation
),
CalculatedAmounts AS (
    SELECT
        AllocatedAmounts.*,
        CAST(UnitStandardCost * Qty AS decimal(19, 4)) AS LineCostAmount
    FROM AllocatedAmounts
)
SELECT
    SaleDateKey,
    CustomerKey,
    StoreKey,
    ProductKey,
    OrderID,
    OrderLineID,
    Qty,
    UnitPrice,
    UnitPriceDiscount,
    GrossSalesAmount,
    DiscountAmount,
    LineNetSalesAmount,
    AllocatedTaxAmount,
    AllocatedFreightAmount,
    CAST(LineNetSalesAmount + AllocatedTaxAmount + AllocatedFreightAmount AS decimal(19, 4)) AS LineTotalDueAmount,
    UnitStandardCost,
    LineCostAmount,
    CAST(LineNetSalesAmount - LineCostAmount AS decimal(19, 4)) AS ProfitAmount
FROM CalculatedAmounts;
GO

/*
    One output row per product and calendar day.
    Only P (purchase) and S (sale) are included. W (work order) is excluded.
*/
CREATE OR ALTER VIEW dbo.vw_FactStock_Source
AS
WITH DailyMovement AS (
    SELECT
        ProductID,
        CAST(TransactionDate AS date) AS MovementDate,
        SUM(CASE WHEN TransactionType = N'P' THEN Quantity ELSE 0 END) AS PurchaseQty,
        SUM(CASE WHEN TransactionType = N'S' THEN Quantity ELSE 0 END) AS SalesQty
    FROM [lh_AdventureWorks_Silver].[cleansed].[InventoryMovement]
    WHERE TransactionType IN (N'P', N'S')
    GROUP BY ProductID, CAST(TransactionDate AS date)
),
FirstMovement AS (
    SELECT ProductID, MIN(MovementDate) AS FirstDate
    FROM DailyMovement
    GROUP BY ProductID
),
DailyBalance AS (
    SELECT
        first_movement.ProductID AS ProductKey,
        date_dimension.DateKey,
        date_dimension.FullDate,
        COALESCE(daily.PurchaseQty, 0) AS PurchaseQty,
        COALESCE(daily.SalesQty, 0) AS SalesQty
    FROM FirstMovement AS first_movement
    INNER JOIN dbo.DimDate AS date_dimension
        ON date_dimension.FullDate >= first_movement.FirstDate
    LEFT JOIN DailyMovement AS daily
        ON daily.ProductID = first_movement.ProductID
       AND daily.MovementDate = date_dimension.FullDate
)
SELECT
    ProductKey,
    DateKey,
    COALESCE(
        SUM(PurchaseQty - SalesQty) OVER (
            PARTITION BY ProductKey
            ORDER BY FullDate
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ),
        0
    ) AS OpeningQty,
    PurchaseQty,
    SalesQty,
    COALESCE(
        SUM(PurchaseQty - SalesQty) OVER (
            PARTITION BY ProductKey
            ORDER BY FullDate
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        0
    ) AS ClosingQty
FROM DailyBalance;
GO
