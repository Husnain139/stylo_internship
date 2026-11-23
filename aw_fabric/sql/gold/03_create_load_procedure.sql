/*
    Run after 01_create_gold_tables.sql and 02_create_gold_source_views.sql.

    The load itself is deliberately simple:
      validate Silver -> begin transaction -> reload dimensions -> reload facts
      -> validate facts -> commit.
*/

CREATE OR ALTER PROCEDURE dbo.usp_Load_Gold
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @ExpectedSalesLines int;
    DECLARE @LoadedSalesLines int;
    DECLARE @SourcePurchaseQty int;
    DECLARE @SourceSalesQty int;
    DECLARE @LoadedPurchaseQty int;
    DECLARE @LoadedSalesQty int;

    BEGIN TRY
        /* Check Silver before changing Gold. */
        SELECT @ExpectedSalesLines = COUNT(*)
        FROM [lh_AdventureWorks_Silver].[cleansed].[SalesOrderDetail];

        IF @ExpectedSalesLines = 0
            THROW 50001, 'Silver SalesOrderDetail is empty.', 1;

        SELECT
            @SourcePurchaseQty = SUM(CASE WHEN TransactionType = N'P' THEN Quantity ELSE 0 END),
            @SourceSalesQty = SUM(CASE WHEN TransactionType = N'S' THEN Quantity ELSE 0 END)
        FROM [lh_AdventureWorks_Silver].[cleansed].[InventoryMovement]
        WHERE TransactionType IN (N'P', N'S');

        BEGIN TRANSACTION;

        /* Clear Gold. The transaction restores old rows if a later step fails. */
        DELETE FROM dbo.FactSales;
        DELETE FROM dbo.FactStock;
        DELETE FROM dbo.DimCustomer;
        DELETE FROM dbo.DimStore;
        DELETE FROM dbo.DimProduct;
        DELETE FROM dbo.DimDate;

        /* DimDate */
        INSERT INTO dbo.DimDate (
            DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
            WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
            IsWeekend, IsWeekday
        )
        SELECT
            DateKey, FullDate, CalendarYear, Quarter, MonthNo, MonthName,
            WeekOfYear, DayOfMonth, DayOfYear, DayOfWeekName, DayOfWeekNo,
            IsWeekend, IsWeekday
        FROM [lh_AdventureWorks_Silver].[cleansed].[Date];

        /* DimCustomer: individual customers plus Unknown (-1). */
        INSERT INTO dbo.DimCustomer (
            CustomerKey, CustomerID, PersonID, AccountNumber, PersonType, Title,
            FirstName, MiddleName, LastName, Suffix, EmailAddress, PhoneNumber,
            PhoneNumberType, AddressLine1, AddressLine2, City, StateProvinceCode,
            StateProvinceName, PostalCode, CountryRegionCode, CountryName,
            SpatialLocation, TerritoryID, TerritoryName, TerritoryGroup
        )
        SELECT
            customer.CustomerID, customer.CustomerID, customer.PersonID,
            COALESCE(customer.AccountNumber, N'Unknown'), person.PersonType,
            person.Title, person.FirstName, person.MiddleName, person.LastName,
            person.Suffix, person.EmailAddress, person.PhoneNumber,
            person.PhoneNumberType, person.AddressLine1, person.AddressLine2,
            person.City, person.StateProvinceCode, person.StateProvinceName,
            person.PostalCode, person.CountryRegionCode, person.CountryName,
            person.SpatialLocation, customer.TerritoryID,
            COALESCE(territory.TerritoryName, N'Unknown'),
            COALESCE(territory.TerritoryGroup, N'Unknown')
        FROM [lh_AdventureWorks_Silver].[cleansed].[Customer] AS customer
        INNER JOIN [lh_AdventureWorks_Silver].[cleansed].[Person] AS person
            ON person.BusinessEntityID = customer.PersonID
        LEFT JOIN [lh_AdventureWorks_Silver].[cleansed].[SalesTerritory] AS territory
            ON territory.TerritoryID = customer.TerritoryID
        WHERE customer.PersonID IS NOT NULL

        UNION ALL

        SELECT
            -1, NULL, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            NULL, N'Unknown', N'Unknown';

        /* DimStore: one Main Office address per store plus Unknown (-1). */
        INSERT INTO dbo.DimStore (
            StoreKey, StoreID, StoreName, AddressLine1, AddressLine2, City,
            StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode,
            CountryName
        )
        SELECT
            StoreID, StoreID, StoreName, AddressLine1, AddressLine2, City,
            StateProvinceCode, StateProvinceName, PostalCode, CountryRegionCode,
            CountryName
        FROM [lh_AdventureWorks_Silver].[cleansed].[Store]

        UNION ALL

        SELECT
            -1, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', N'Unknown', N'Unknown', N'Unknown';

        /* DimProduct: products plus Unknown (-1). */
        INSERT INTO dbo.DimProduct (
            ProductKey, ProductID, ProductName, ProductNumber, Color, Category,
            Subcategory, Size, Weight, SizeUnit, WeightUnit, Class, Style,
            StandardCost, Discontinued, DiscontinuedDate, ModifiedDate
        )
        SELECT
            ProductID, ProductID, Name, ProductNumber, Color, Category,
            Subcategory, Size, Weight, SizeUnit, WeightUnit, Class, Style,
            StandardCost, Discontinued, DiscontinuedDate, ModifiedDate
        FROM [lh_AdventureWorks_Silver].[cleansed].[Product]

        UNION ALL

        SELECT
            -1, NULL, N'Unknown', N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', N'Unknown', NULL, N'Unknown', N'Unknown', N'Unknown',
            N'Unknown', 0, 0, NULL, NULL;

        /* FactSales and FactStock use the readable source views. */
        INSERT INTO dbo.FactSales (
            SaleDateKey, CustomerKey, StoreKey, ProductKey, OrderID, OrderLineID,
            Qty, UnitPrice, UnitPriceDiscount, GrossSalesAmount, DiscountAmount,
            LineNetSalesAmount, AllocatedTaxAmount, AllocatedFreightAmount, LineTotalDueAmount,
            UnitStandardCost, LineCostAmount, ProfitAmount
        )
        SELECT
            SaleDateKey, CustomerKey, StoreKey, ProductKey, OrderID, OrderLineID,
            Qty, UnitPrice, UnitPriceDiscount, GrossSalesAmount, DiscountAmount,
            LineNetSalesAmount, AllocatedTaxAmount, AllocatedFreightAmount, LineTotalDueAmount,
            UnitStandardCost, LineCostAmount, ProfitAmount
        FROM dbo.vw_FactSales_Source;

        SELECT @LoadedSalesLines = COUNT(*) FROM dbo.FactSales;

        IF @LoadedSalesLines <> @ExpectedSalesLines
            THROW 50002, 'FactSales row count does not match Silver SalesOrderDetail.', 1;

        INSERT INTO dbo.FactStock (
            ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
        )
        SELECT
            ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
        FROM dbo.vw_FactStock_Source;

        SELECT
            @LoadedPurchaseQty = SUM(PurchaseQty),
            @LoadedSalesQty = SUM(SalesQty)
        FROM dbo.FactStock;

        IF COALESCE(@SourcePurchaseQty, 0) <> COALESCE(@LoadedPurchaseQty, 0)
           OR COALESCE(@SourceSalesQty, 0) <> COALESCE(@LoadedSalesQty, 0)
            THROW 50003, 'FactStock quantities do not match Silver InventoryMovement.', 1;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        INSERT INTO dbo.ETL_Log (
            ProcedureName, ErrorNumber, ErrorMessage, ErrorLine, LoggedAt
        )
        VALUES (
            N'dbo.usp_Load_Gold', ERROR_NUMBER(), ERROR_MESSAGE(), ERROR_LINE(), SYSUTCDATETIME()
        );

        THROW;
    END CATCH
END;
GO
