/*
    Run once in wh_AdventureWorks_Gold.
    Each block creates a table only if it does not already exist.
*/

IF OBJECT_ID(N'dbo.DimDate', N'U') IS NULL
BEGIN
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
END;
GO

IF OBJECT_ID(N'dbo.DimCustomer', N'U') IS NULL
BEGIN
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
END;
GO

IF OBJECT_ID(N'dbo.DimStore', N'U') IS NULL
BEGIN
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
END;
GO

IF OBJECT_ID(N'dbo.DimProduct', N'U') IS NULL
BEGIN
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
END;
GO

IF OBJECT_ID(N'dbo.FactSales', N'U') IS NULL
BEGIN
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
        GrossSalesAmount decimal(19, 4) NOT NULL,
        DiscountAmount decimal(19, 4) NOT NULL,
        LineNetSalesAmount decimal(19, 4) NOT NULL,
        AllocatedTaxAmount decimal(19, 4) NOT NULL,
        AllocatedFreightAmount decimal(19, 4) NOT NULL,
        LineTotalDueAmount decimal(19, 4) NOT NULL,
        UnitStandardCost decimal(19, 4) NOT NULL,
        LineCostAmount decimal(19, 4) NOT NULL,
        ProfitAmount decimal(19, 4) NOT NULL,
        CONSTRAINT PK_FactSales PRIMARY KEY NONCLUSTERED (SaleKey) NOT ENFORCED,
        CONSTRAINT FK_FactSales_Date FOREIGN KEY (SaleDateKey) REFERENCES dbo.DimDate (DateKey) NOT ENFORCED,
        CONSTRAINT FK_FactSales_Customer FOREIGN KEY (CustomerKey) REFERENCES dbo.DimCustomer (CustomerKey) NOT ENFORCED,
        CONSTRAINT FK_FactSales_Store FOREIGN KEY (StoreKey) REFERENCES dbo.DimStore (StoreKey) NOT ENFORCED,
        CONSTRAINT FK_FactSales_Product FOREIGN KEY (ProductKey) REFERENCES dbo.DimProduct (ProductKey) NOT ENFORCED
    );
END;
GO

IF OBJECT_ID(N'dbo.FactStock', N'U') IS NULL
BEGIN
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
END;
GO
