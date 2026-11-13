/*
    Run this in wh_AdventureWorks_Gold.

    Silver must already be loaded. The warehouse reads it as
    lh_AdventureWorks_Silver.cleansed. If a name cannot be found, open the
    Silver SQL analytics endpoint, refresh its metadata, and run this again.

    Staging is loaded first. dbo is replaced only after the row counts match,
    inside one transaction. A failure leaves the previous Gold tables in place
    and writes one row to dbo.ETL_Log.
*/

IF SCHEMA_ID(N'stg') IS NULL
    EXEC(N'CREATE SCHEMA stg');
GO

DROP TABLE IF EXISTS dbo.FactSales;
DROP TABLE IF EXISTS dbo.FactStock;
DROP TABLE IF EXISTS dbo.DimCustomer;
DROP TABLE IF EXISTS dbo.DimStore;
DROP TABLE IF EXISTS dbo.DimProduct;
DROP TABLE IF EXISTS dbo.DimDate;
DROP TABLE IF EXISTS stg.FactSales;
DROP TABLE IF EXISTS stg.FactStock;
DROP TABLE IF EXISTS stg.Movement;
DROP TABLE IF EXISTS stg.ProductCost;
DROP TABLE IF EXISTS stg.Customer;
DROP TABLE IF EXISTS stg.Person;
DROP TABLE IF EXISTS stg.Store;
DROP TABLE IF EXISTS stg.Product;
DROP TABLE IF EXISTS stg.Territory;
DROP TABLE IF EXISTS stg.Header;
DROP TABLE IF EXISTS stg.Detail;
DROP TABLE IF EXISTS stg.DimDate;
GO

CREATE TABLE stg.DimDate (
    DateKey int NOT NULL,
    FullDate date NOT NULL,
    CalendarYear int NOT NULL,
    Quarter int NOT NULL,
    MonthNo int NOT NULL,
    MonthName nvarchar(20) NOT NULL,
    WeekOfYear int NOT NULL,
    DayOfMonth int NOT NULL,
    DayOfYear int NOT NULL,
    DayOfWeekName nvarchar(20) NOT NULL,
    DayOfWeekNo int NOT NULL,
    IsWeekend bit NOT NULL,
    IsWeekday bit NOT NULL
);

CREATE TABLE stg.Header (
    SalesOrderID int NOT NULL,
    CustomerID int NOT NULL,
    OrderDate datetime2(6) NOT NULL,
    SubTotal decimal(19, 4) NOT NULL,
    TaxAmt decimal(19, 4) NOT NULL,
    Freight decimal(19, 4) NOT NULL
);

CREATE TABLE stg.Detail (
    SalesOrderID int NOT NULL,
    SalesOrderDetailID int NOT NULL,
    OrderQty int NOT NULL,
    ProductID int NOT NULL,
    UnitPrice decimal(19, 4) NOT NULL,
    UnitPriceDiscount decimal(19, 4) NOT NULL
);

CREATE TABLE stg.Customer (
    CustomerID int NOT NULL,
    PersonID int NULL,
    StoreID int NULL,
    TerritoryID int NULL,
    AccountNumber nvarchar(20) NULL
);

CREATE TABLE stg.Person (
    BusinessEntityID int NOT NULL,
    PersonType nvarchar(10) NOT NULL,
    Title nvarchar(20) NOT NULL,
    FirstName nvarchar(50) NOT NULL,
    MiddleName nvarchar(50) NOT NULL,
    LastName nvarchar(50) NOT NULL,
    Suffix nvarchar(20) NOT NULL,
    EmailAddress nvarchar(100) NOT NULL,
    PhoneNumber nvarchar(50) NOT NULL,
    PhoneNumberType nvarchar(50) NOT NULL,
    AddressLine1 nvarchar(200) NOT NULL,
    AddressLine2 nvarchar(200) NOT NULL,
    City nvarchar(100) NOT NULL,
    StateProvinceCode nvarchar(10) NOT NULL,
    StateProvinceName nvarchar(100) NOT NULL,
    PostalCode nvarchar(20) NOT NULL,
    CountryRegionCode nvarchar(10) NOT NULL,
    CountryName nvarchar(100) NOT NULL,
    SpatialLocation nvarchar(max) NOT NULL
);

CREATE TABLE stg.Store (
    StoreID int NOT NULL,
    StoreName nvarchar(100) NOT NULL,
    AddressLine1 nvarchar(200) NOT NULL,
    AddressLine2 nvarchar(200) NOT NULL,
    City nvarchar(100) NOT NULL,
    StateProvinceCode nvarchar(10) NOT NULL,
    StateProvinceName nvarchar(100) NOT NULL,
    PostalCode nvarchar(20) NOT NULL,
    CountryRegionCode nvarchar(10) NOT NULL,
    CountryName nvarchar(100) NOT NULL
);

CREATE TABLE stg.Territory (
    TerritoryID int NOT NULL,
    TerritoryName nvarchar(100) NOT NULL,
    CountryRegionCode nvarchar(10) NOT NULL,
    TerritoryGroup nvarchar(100) NOT NULL
);

CREATE TABLE stg.Product (
    ProductID int NOT NULL,
    ProductName nvarchar(100) NOT NULL,
    ProductNumber nvarchar(50) NOT NULL,
    Color nvarchar(30) NOT NULL,
    Category nvarchar(100) NOT NULL,
    Subcategory nvarchar(100) NOT NULL,
    Size nvarchar(10) NOT NULL,
    Weight decimal(8, 2) NULL,
    SizeUnit nvarchar(50) NOT NULL,
    WeightUnit nvarchar(50) NOT NULL,
    Class nvarchar(10) NOT NULL,
    Style nvarchar(10) NOT NULL,
    StandardCost decimal(19, 4) NOT NULL,
    Discontinued bit NOT NULL,
    DiscontinuedDate datetime2(6) NULL,
    ModifiedDate datetime2(6) NOT NULL
);

CREATE TABLE stg.ProductCost (
    ProductID int NOT NULL,
    StartDate date NOT NULL,
    EndDate date NULL,
    StandardCost decimal(19, 4) NOT NULL
);

CREATE TABLE stg.Movement (
    ProductID int NOT NULL,
    TransactionDate datetime2(6) NOT NULL,
    TransactionType nvarchar(2) NOT NULL,
    Quantity int NOT NULL
);

CREATE TABLE stg.FactSales (
    SaleDateKey int NOT NULL,
    CustomerKey int NOT NULL,
    StoreKey int NOT NULL,
    ProductKey int NOT NULL,
    OrderID int NOT NULL,
    OrderLineID int NOT NULL,
    Qty int NOT NULL,
    UnitPrice decimal(19, 4) NOT NULL,
    UnitPriceDiscount decimal(19, 4) NOT NULL,
    GrossPrice decimal(19, 4) NOT NULL,
    NetPrice decimal(19, 4) NOT NULL,
    Tax decimal(19, 4) NOT NULL,
    Freight decimal(19, 4) NOT NULL,
    StandardCost decimal(19, 4) NOT NULL
);

CREATE TABLE stg.FactStock (
    ProductKey int NOT NULL,
    DateKey int NOT NULL,
    OpeningQty int NOT NULL,
    PurchaseQty int NOT NULL,
    SalesQty int NOT NULL,
    ClosingQty int NOT NULL
);
GO

CREATE TABLE dbo.DimDate (
    DateKey int NOT NULL,
    FullDate date NOT NULL,
    CalendarYear int NOT NULL,
    Quarter int NOT NULL,
    MonthNo int NOT NULL,
    MonthName nvarchar(20) NOT NULL,
    WeekOfYear int NOT NULL,
    DayOfMonth int NOT NULL,
    DayOfYear int NOT NULL,
    DayOfWeekName nvarchar(20) NOT NULL,
    DayOfWeekNo int NOT NULL,
    IsWeekend bit NOT NULL,
    IsWeekday bit NOT NULL,
    CONSTRAINT PK_DimDate PRIMARY KEY NONCLUSTERED (DateKey) NOT ENFORCED
);

CREATE TABLE dbo.DimCustomer (
    CustomerKey int NOT NULL,
    CustomerID int NULL,
    PersonID int NULL,
    AccountNumber nvarchar(20) NOT NULL,
    PersonType nvarchar(10) NOT NULL,
    Title nvarchar(20) NOT NULL,
    FirstName nvarchar(50) NOT NULL,
    MiddleName nvarchar(50) NOT NULL,
    LastName nvarchar(50) NOT NULL,
    Suffix nvarchar(20) NOT NULL,
    EmailAddress nvarchar(100) NOT NULL,
    PhoneNumber nvarchar(50) NOT NULL,
    PhoneNumberType nvarchar(50) NOT NULL,
    AddressLine1 nvarchar(200) NOT NULL,
    AddressLine2 nvarchar(200) NOT NULL,
    City nvarchar(100) NOT NULL,
    StateProvinceCode nvarchar(10) NOT NULL,
    StateProvinceName nvarchar(100) NOT NULL,
    PostalCode nvarchar(20) NOT NULL,
    CountryRegionCode nvarchar(10) NOT NULL,
    CountryName nvarchar(100) NOT NULL,
    SpatialLocation nvarchar(max) NOT NULL,
    TerritoryID int NULL,
    TerritoryName nvarchar(100) NOT NULL,
    TerritoryGroup nvarchar(100) NOT NULL,
    CONSTRAINT PK_DimCustomer PRIMARY KEY NONCLUSTERED (CustomerKey) NOT ENFORCED
);

CREATE TABLE dbo.DimStore (
    StoreKey int NOT NULL,
    StoreID int NULL,
    StoreName nvarchar(100) NOT NULL,
    AddressLine1 nvarchar(200) NOT NULL,
    AddressLine2 nvarchar(200) NOT NULL,
    City nvarchar(100) NOT NULL,
    StateProvinceCode nvarchar(10) NOT NULL,
    StateProvinceName nvarchar(100) NOT NULL,
    PostalCode nvarchar(20) NOT NULL,
    CountryRegionCode nvarchar(10) NOT NULL,
    CountryName nvarchar(100) NOT NULL,
    CONSTRAINT PK_DimStore PRIMARY KEY NONCLUSTERED (StoreKey) NOT ENFORCED
);

CREATE TABLE dbo.DimProduct (
    ProductKey int NOT NULL,
    ProductID int NULL,
    ProductName nvarchar(100) NOT NULL,
    ProductNumber nvarchar(50) NOT NULL,
    Color nvarchar(30) NOT NULL,
    Category nvarchar(100) NOT NULL,
    Subcategory nvarchar(100) NOT NULL,
    Size nvarchar(10) NOT NULL,
    Weight decimal(8, 2) NULL,
    SizeUnit nvarchar(50) NOT NULL,
    WeightUnit nvarchar(50) NOT NULL,
    Class nvarchar(10) NOT NULL,
    Style nvarchar(10) NOT NULL,
    StandardCost decimal(19, 4) NOT NULL,
    Discontinued bit NOT NULL,
    DiscontinuedDate datetime2(6) NULL,
    ModifiedDate datetime2(6) NULL,
    CONSTRAINT PK_DimProduct PRIMARY KEY NONCLUSTERED (ProductKey) NOT ENFORCED
);

CREATE TABLE dbo.FactSales (
    SaleKey bigint IDENTITY NOT NULL,
    SaleDateKey int NOT NULL,
    CustomerKey int NOT NULL,
    StoreKey int NOT NULL,
    ProductKey int NOT NULL,
    OrderID int NOT NULL,
    OrderLineID int NOT NULL,
    Qty int NOT NULL,
    UnitPrice decimal(19, 4) NOT NULL,
    UnitPriceDiscount decimal(19, 4) NOT NULL,
    GrossPrice decimal(19, 4) NOT NULL,
    NetPrice decimal(19, 4) NOT NULL,
    Tax decimal(19, 4) NOT NULL,
    Freight decimal(19, 4) NOT NULL,
    StandardCost decimal(19, 4) NOT NULL,
    CONSTRAINT PK_FactSales PRIMARY KEY NONCLUSTERED (SaleKey) NOT ENFORCED,
    CONSTRAINT FK_FactSales_Date FOREIGN KEY (SaleDateKey) REFERENCES dbo.DimDate (DateKey) NOT ENFORCED,
    CONSTRAINT FK_FactSales_Customer FOREIGN KEY (CustomerKey) REFERENCES dbo.DimCustomer (CustomerKey) NOT ENFORCED,
    CONSTRAINT FK_FactSales_Store FOREIGN KEY (StoreKey) REFERENCES dbo.DimStore (StoreKey) NOT ENFORCED,
    CONSTRAINT FK_FactSales_Product FOREIGN KEY (ProductKey) REFERENCES dbo.DimProduct (ProductKey) NOT ENFORCED
);

CREATE TABLE dbo.FactStock (
    StockKey bigint IDENTITY NOT NULL,
    ProductKey int NOT NULL,
    DateKey int NOT NULL,
    OpeningQty int NOT NULL,
    PurchaseQty int NOT NULL,
    SalesQty int NOT NULL,
    ClosingQty int NOT NULL,
    CONSTRAINT PK_FactStock PRIMARY KEY NONCLUSTERED (StockKey) NOT ENFORCED,
    CONSTRAINT FK_FactStock_Date FOREIGN KEY (DateKey) REFERENCES dbo.DimDate (DateKey) NOT ENFORCED,
    CONSTRAINT FK_FactStock_Product FOREIGN KEY (ProductKey) REFERENCES dbo.DimProduct (ProductKey) NOT ENFORCED
);
GO

CREATE OR ALTER PROCEDURE dbo.usp_Load_Gold
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @silver_lines int;
    DECLARE @staged_lines int;
    DECLARE @source_purchase int;
    DECLARE @source_sales int;
    DECLARE @stock_purchase int;
    DECLARE @stock_sales int;

    DELETE FROM stg.FactSales;
    DELETE FROM stg.FactStock;
    DELETE FROM stg.Movement;
    DELETE FROM stg.ProductCost;
    DELETE FROM stg.Customer;
    DELETE FROM stg.Person;
    DELETE FROM stg.Store;
    DELETE FROM stg.Product;
    DELETE FROM stg.Territory;
    DELETE FROM stg.Header;
    DELETE FROM stg.Detail;
    DELETE FROM stg.DimDate;

    INSERT INTO stg.DimDate (
        DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
        WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
        IsWeekend, IsWeekday
    )
    SELECT
        DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
        WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
        IsWeekend, IsWeekday
    FROM [lh_AdventureWorks_Silver].[cleansed].[Date];

    INSERT INTO stg.Header (SalesOrderID, CustomerID, OrderDate, SubTotal, TaxAmt, Freight)
    SELECT SalesOrderID, CustomerID, OrderDate, SubTotal, TaxAmt, Freight
    FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderHeader];

    INSERT INTO stg.Detail (
        SalesOrderID, SalesOrderDetailID, OrderQty, ProductID, UnitPrice, UnitPriceDiscount
    )
    SELECT
        SalesOrderID, SalesOrderDetailID, OrderQty, ProductID, UnitPrice,
        ISNULL(UnitPriceDiscount, 0)
    FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderDetail];

    INSERT INTO stg.Customer (CustomerID, PersonID, StoreID, TerritoryID, AccountNumber)
    SELECT CustomerID, PersonID, StoreID, TerritoryID, AccountNumber
    FROM [lh_AdventureWorks_Silver].[cleansed].[Customer];

    INSERT INTO stg.Person (
        BusinessEntityID, PersonType, Title, FirstName, MiddleName, LastName, Suffix,
        EmailAddress, PhoneNumber, PhoneNumberType, AddressLine1, AddressLine2, City,
        StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode, CountryName,
        SpatialLocation
    )
    SELECT
        BusinessEntityID, PersonType, Title, FirstName, MiddleName, LastName, Suffix,
        EmailAddress, PhoneNumber, PhoneNumberType, AddressLine1, AddressLine2, City,
        StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode, CountryName,
        SpatialLocation
    FROM [lh_AdventureWorks_Silver].[cleansed].[Person];

    INSERT INTO stg.Store (
        StoreID, StoreName, AddressLine1, AddressLine2, City, StateProvinceCode,
        StateProvinceName, PostalCode, CountryRegionCode, CountryName
    )
    SELECT
        StoreID, StoreName, AddressLine1, AddressLine2, City, StateProvinceCode,
        StateProvinceName, PostalCode, CountryRegionCode, CountryName
    FROM [lh_AdventureWorks_Silver].[cleansed].[Store];

    INSERT INTO stg.Territory (TerritoryID, TerritoryName, CountryRegionCode, TerritoryGroup)
    SELECT TerritoryID, TerritoryName, CountryRegionCode, TerritoryGroup
    FROM [lh_AdventureWorks_Silver].[cleansed].[SalesTerritory];

    INSERT INTO stg.Product (
        ProductID, ProductName, ProductNumber, Color, Category, Subcategory, Size, Weight,
        SizeUnit, WeightUnit, Class, Style, StandardCost, Discontinued, DiscontinuedDate,
        ModifiedDate
    )
    SELECT
        ProductID, Name, ProductNumber, Color, Category, Subcategory, Size, Weight,
        SizeUnit, WeightUnit, Class, Style, StandardCost, Discontinued, DiscontinuedDate,
        ModifiedDate
    FROM [lh_AdventureWorks_Silver].[cleansed].[Product];

    INSERT INTO stg.ProductCost (ProductID, StartDate, EndDate, StandardCost)
    SELECT ProductID, StartDate, EndDate, StandardCost
    FROM [lh_AdventureWorks_Silver].[cleansed].[ProductCostHistory];

    INSERT INTO stg.Movement (ProductID, TransactionDate, TransactionType, Quantity)
    SELECT ProductID, TransactionDate, TransactionType, Quantity
    FROM [lh_AdventureWorks_Silver].[cleansed].[InventoryMovement];

    INSERT INTO stg.FactSales (
        SaleDateKey, CustomerKey, StoreKey, ProductKey, OrderID, OrderLineID, Qty,
        UnitPrice, UnitPriceDiscount, GrossPrice, NetPrice, Tax, Freight, StandardCost
    )
    SELECT
        priced.DateKey,
        priced.CustomerKey,
        priced.StoreKey,
        priced.ProductKey,
        priced.SalesOrderID,
        priced.SalesOrderDetailID,
        priced.OrderQty,
        priced.UnitPrice,
        priced.UnitPriceDiscount,
        priced.GrossPrice,
        priced.NetPrice,
        CAST(
            priced.TaxRaw + CASE
                WHEN priced.LineRank = 1 THEN priced.TaxAmt - SUM(priced.TaxRaw) OVER (PARTITION BY priced.SalesOrderID)
                ELSE 0
            END
            AS decimal(19, 4)
        ),
        CAST(
            priced.FreightRaw + CASE
                WHEN priced.LineRank = 1 THEN priced.Freight - SUM(priced.FreightRaw) OVER (PARTITION BY priced.SalesOrderID)
                ELSE 0
            END
            AS decimal(19, 4)
        ),
        priced.StandardCost
    FROM (
        SELECT
            lines.SalesOrderID,
            lines.SalesOrderDetailID,
            lines.OrderQty,
            lines.UnitPrice,
            lines.UnitPriceDiscount,
            lines.GrossPrice,
            lines.NetPrice,
            lines.SubTotal,
            lines.TaxAmt,
            lines.Freight,
            lines.LineRank,
            lines.DateKey,
            lines.CustomerKey,
            lines.StoreKey,
            lines.ProductKey,
            lines.StandardCost,
            CASE
                WHEN lines.SubTotal = 0 AND lines.LineRank = 1 THEN lines.TaxAmt
                WHEN lines.SubTotal = 0 THEN CAST(0 AS decimal(19, 4))
                ELSE CAST(lines.TaxAmt * lines.NetPrice / lines.SubTotal AS decimal(19, 4))
            END AS TaxRaw,
            CASE
                WHEN lines.SubTotal = 0 AND lines.LineRank = 1 THEN lines.Freight
                WHEN lines.SubTotal = 0 THEN CAST(0 AS decimal(19, 4))
                ELSE CAST(lines.Freight * lines.NetPrice / lines.SubTotal AS decimal(19, 4))
            END AS FreightRaw
        FROM (
            SELECT
                detail.SalesOrderID,
                detail.SalesOrderDetailID,
                detail.OrderQty,
                detail.UnitPrice,
                detail.UnitPriceDiscount,
                CAST(detail.UnitPrice * detail.OrderQty AS decimal(19, 4)) AS GrossPrice,
                CAST(detail.UnitPrice * detail.OrderQty * (1 - detail.UnitPriceDiscount) AS decimal(19, 4)) AS NetPrice,
                header.SubTotal,
                header.TaxAmt,
                header.Freight,
                ROW_NUMBER() OVER (PARTITION BY detail.SalesOrderID ORDER BY detail.SalesOrderDetailID) AS LineRank,
                dim_date.DateKey,
                CASE WHEN customer.PersonID IS NULL THEN -1 ELSE customer.CustomerID END AS CustomerKey,
                CASE
                    WHEN customer.StoreID IS NULL OR store.StoreID IS NULL THEN -1
                    ELSE customer.StoreID
                END AS StoreKey,
                CASE WHEN product.ProductID IS NULL THEN -1 ELSE detail.ProductID END AS ProductKey,
                COALESCE(cost_history.StandardCost, product.StandardCost, CAST(0 AS decimal(19, 4))) AS StandardCost
            FROM stg.Detail AS detail
            INNER JOIN stg.Header AS header
                ON header.SalesOrderID = detail.SalesOrderID
            INNER JOIN stg.Customer AS customer
                ON customer.CustomerID = header.CustomerID
            INNER JOIN stg.DimDate AS dim_date
                ON dim_date.FullDate = CAST(header.OrderDate AS date)
            LEFT JOIN stg.Store AS store
                ON store.StoreID = customer.StoreID
            LEFT JOIN stg.Product AS product
                ON product.ProductID = detail.ProductID
            OUTER APPLY (
                SELECT TOP (1) history.StandardCost
                FROM stg.ProductCost AS history
                WHERE history.ProductID = detail.ProductID
                  AND history.StartDate <= CAST(header.OrderDate AS date)
                  AND (history.EndDate IS NULL OR history.EndDate > CAST(header.OrderDate AS date))
                ORDER BY history.StartDate DESC
            ) AS cost_history
        ) AS lines
    ) AS priced;

    SELECT @silver_lines = COUNT(*) FROM stg.Detail;
    SELECT @staged_lines = COUNT(*) FROM stg.FactSales;
    IF @silver_lines = 0 OR @silver_lines <> @staged_lines
        THROW 50001, 'FactSales staging does not match Silver order lines.', 1;

    INSERT INTO stg.FactStock (ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty)
    SELECT
        grid.ProductKey,
        grid.DateKey,
        grid.OpeningQty,
        grid.PurchaseQty,
        grid.SalesQty,
        grid.OpeningQty + grid.PurchaseQty - grid.SalesQty
    FROM (
        SELECT
            span.ProductID AS ProductKey,
            dim_date.DateKey,
            COALESCE(daily.PurchaseQty, 0) AS PurchaseQty,
            COALESCE(daily.SalesQty, 0) AS SalesQty,
            COALESCE(
                SUM(COALESCE(daily.PurchaseQty, 0) - COALESCE(daily.SalesQty, 0)) OVER (
                    PARTITION BY span.ProductID
                    ORDER BY dim_date.FullDate
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ),
                0
            ) AS OpeningQty
        FROM (
            SELECT ProductID, MIN(CAST(TransactionDate AS date)) AS FirstDate
            FROM stg.Movement
            WHERE TransactionType IN (N'P', N'S')
            GROUP BY ProductID
        ) AS span
        INNER JOIN stg.DimDate AS dim_date
            ON dim_date.FullDate >= span.FirstDate
        LEFT JOIN (
            SELECT
                ProductID,
                CAST(TransactionDate AS date) AS MovementDate,
                SUM(CASE WHEN TransactionType = N'P' THEN Quantity ELSE 0 END) AS PurchaseQty,
                SUM(CASE WHEN TransactionType = N'S' THEN Quantity ELSE 0 END) AS SalesQty
            FROM stg.Movement
            WHERE TransactionType IN (N'P', N'S')
            GROUP BY ProductID, CAST(TransactionDate AS date)
        ) AS daily
            ON daily.ProductID = span.ProductID
           AND daily.MovementDate = dim_date.FullDate
    ) AS grid;

    SELECT @source_purchase = SUM(Quantity) FROM stg.Movement WHERE TransactionType = N'P';
    SELECT @source_sales = SUM(Quantity) FROM stg.Movement WHERE TransactionType = N'S';
    SELECT @stock_purchase = SUM(PurchaseQty), @stock_sales = SUM(SalesQty) FROM stg.FactStock;
    IF ISNULL(@source_purchase, 0) <> ISNULL(@stock_purchase, 0)
        OR ISNULL(@source_sales, 0) <> ISNULL(@stock_sales, 0)
        THROW 50002, 'FactStock purchase or sales quantity does not match Silver.', 1;

    BEGIN TRY
        BEGIN TRANSACTION;

        DELETE FROM dbo.FactSales;
        DELETE FROM dbo.FactStock;
        DELETE FROM dbo.DimCustomer;
        DELETE FROM dbo.DimStore;
        DELETE FROM dbo.DimProduct;
        DELETE FROM dbo.DimDate;

        INSERT INTO dbo.DimDate (
            DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
            WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
            IsWeekend, IsWeekday
        )
        SELECT
            DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
            WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
            IsWeekend, IsWeekday
        FROM stg.DimDate;

        INSERT INTO dbo.DimCustomer (
            CustomerKey, CustomerID, PersonID, AccountNumber, PersonType, Title, FirstName,
            MiddleName, LastName, Suffix, EmailAddress, PhoneNumber, PhoneNumberType,
            AddressLine1, AddressLine2, City, StateProvinceCode, StateProvinceName,
            PostalCode, CountryRegionCode, CountryName, SpatialLocation, TerritoryID,
            TerritoryName, TerritoryGroup
        )
        SELECT
            customer.CustomerID,
            customer.CustomerID,
            customer.PersonID,
            ISNULL(customer.AccountNumber, N'Unknown'),
            person.PersonType,
            person.Title,
            person.FirstName,
            person.MiddleName,
            person.LastName,
            person.Suffix,
            person.EmailAddress,
            person.PhoneNumber,
            person.PhoneNumberType,
            person.AddressLine1,
            person.AddressLine2,
            person.City,
            person.StateProvinceCode,
            person.StateProvinceName,
            person.PostalCode,
            person.CountryRegionCode,
            person.CountryName,
            person.SpatialLocation,
            customer.TerritoryID,
            ISNULL(territory.TerritoryName, N'Unknown'),
            ISNULL(territory.TerritoryGroup, N'Unknown')
        FROM stg.Customer AS customer
        INNER JOIN stg.Person AS person
            ON person.BusinessEntityID = customer.PersonID
        LEFT JOIN stg.Territory AS territory
            ON territory.TerritoryID = customer.TerritoryID
        WHERE customer.PersonID IS NOT NULL

        UNION ALL

        SELECT
            -1, NULL, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', NULL, N'Unknown', N'Unknown';

        INSERT INTO dbo.DimStore (
            StoreKey, StoreID, StoreName, AddressLine1, AddressLine2, City,
            StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode, CountryName
        )
        SELECT
            StoreID, StoreID, StoreName, AddressLine1, AddressLine2, City,
            StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode, CountryName
        FROM stg.Store

        UNION ALL

        SELECT
            -1, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown';

        INSERT INTO dbo.DimProduct (
            ProductKey, ProductID, ProductName, ProductNumber, Color, Category, Subcategory,
            Size, Weight, SizeUnit, WeightUnit, Class, Style, StandardCost, Discontinued,
            DiscontinuedDate, ModifiedDate
        )
        SELECT
            ProductID, ProductID, ProductName, ProductNumber, Color, Category, Subcategory,
            Size, Weight, SizeUnit, WeightUnit, Class, Style, StandardCost,
            Discontinued, DiscontinuedDate, ModifiedDate
        FROM stg.Product

        UNION ALL

        SELECT
            -1, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            0, 0, NULL, NULL;

        INSERT INTO dbo.FactSales (
            SaleDateKey, CustomerKey, StoreKey, ProductKey, OrderID, OrderLineID, Qty,
            UnitPrice, UnitPriceDiscount, GrossPrice, NetPrice, Tax, Freight, StandardCost
        )
        SELECT
            SaleDateKey, CustomerKey, StoreKey, ProductKey, OrderID, OrderLineID, Qty,
            UnitPrice, UnitPriceDiscount, GrossPrice, NetPrice, Tax, Freight, StandardCost
        FROM stg.FactSales;

        INSERT INTO dbo.FactStock (
            ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
        )
        SELECT ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
        FROM stg.FactStock;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        INSERT INTO dbo.ETL_Log (ProcedureName, ErrorNumber, ErrorMessage, ErrorLine, LoggedAt)
        VALUES (N'dbo.usp_Load_Gold', ERROR_NUMBER(), ERROR_MESSAGE(), ERROR_LINE(), SYSUTCDATETIME());

        THROW;
    END CATCH
END;
GO

EXEC dbo.usp_Load_Gold;
GO

SELECT N'FactSales' AS CheckName, COUNT(*) AS RowsFound, 121317 AS RowsExpected
FROM dbo.FactSales
UNION ALL
SELECT N'DimCustomer', COUNT(*), 19120 FROM dbo.DimCustomer
UNION ALL
SELECT N'DimStore', COUNT(*), 702 FROM dbo.DimStore
UNION ALL
SELECT N'DimProduct', COUNT(*), 505 FROM dbo.DimProduct
UNION ALL
SELECT N'DimDate', COUNT(*), 1461 FROM dbo.DimDate;

SELECT
    COUNT(*) AS OrdersChecked,
    SUM(CASE WHEN ABS(header.TaxAmt - lines.Tax) > 0 THEN 1 ELSE 0 END) AS OrdersTaxOff,
    SUM(CASE WHEN ABS(header.Freight - lines.Freight) > 0 THEN 1 ELSE 0 END) AS OrdersFreightOff
FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderHeader] AS header
INNER JOIN (
    SELECT OrderID, SUM(Tax) AS Tax, SUM(Freight) AS Freight
    FROM dbo.FactSales
    GROUP BY OrderID
) AS lines
    ON lines.OrderID = header.SalesOrderID;

SELECT
    SUM(CASE WHEN ranked.rn = 1 AND ranked.OpeningQty <> 0 THEN 1 ELSE 0 END) AS ProductsWhoseFirstDayIsNotZero
FROM (
    SELECT
        ProductKey,
        OpeningQty,
        ROW_NUMBER() OVER (PARTITION BY ProductKey ORDER BY DateKey) AS rn
    FROM dbo.FactStock
) AS ranked;

SELECT COUNT(*) AS EtlLogRows FROM dbo.ETL_Log;
GO
