/*
    Simple Gold load: run this top to bottom in wh_AdventureWorks_Gold.

    Prerequisites:
      - 01_create_gold_tables.sql was run once.
      - 02_create_gold_source_views.sql was run once.

    This is intentionally a learning/manual version:
      - no stored procedure
      - no transaction
      - no validation queries

    Do not use it for a scheduled production refresh. If a statement fails,
    tables loaded earlier in this script remain changed.
*/

/* Cell 1: remove the previous Gold rows. */
DELETE FROM dbo.FactSales;
DELETE FROM dbo.FactStock;
DELETE FROM dbo.DimCustomer;
DELETE FROM dbo.DimStore;
DELETE FROM dbo.DimProduct;
DELETE FROM dbo.DimDate;
GO

/* Cell 2: load the calendar. */
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
GO

/* Cell 3: load individual customers and one Unknown member. */
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
GO

/* Cell 4: load stores and one Unknown member. */
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
GO

/* Cell 5: load products and one Unknown member. */
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
GO

/* Cell 6: load one row per order line from the sales source view. */
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
GO

/* Cell 7: load one row per product and calendar day from the stock source view. */
INSERT INTO dbo.FactStock (
    ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
)
SELECT
    ProductKey, DateKey, OpeningQty, PurchaseQty, SalesQty, ClosingQty
FROM dbo.vw_FactStock_Source;
GO
