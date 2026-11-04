# AGENTS.md: AdventureWorks2025 Medallion Project

Read this file first, then the extracts in `docs/source/`.

## 1. Project summary

Medallion project on a Fabric trial capacity. The source is AdventureWorks2025 on SQL Server 2025, through the on-premises data gateway. `AdventureWorksDW2025` is the Gold shape only. Do not load it into Fabric. Do not restore the OLTP database. Database CDC stays enabled and no table is captured.

```
SQL Server 2025 -> gateway -> lh_AdventureWorks_Bronze (69 raw Delta tables)
                           -> lh_AdventureWorks_Silver (cleansed schema, Gold inputs only)
                           -> wh_AdventureWorks_Gold   (sales star, T-SQL)
                           -> Power BI semantic model (Direct Lake on OneLake)
```

Spark cleans. The warehouse loads Gold in one transaction. Purchasing, work orders, and inventory stay in Bronze.

## 2. Source of truth

- `docs/source/adventure_works.txt`: OLTP tables, keys, foreign keys, row counts
- `docs/source/adventure_works_dw.txt`: warehouse shape, keys, foreign keys, row counts
- `docs/decisions.md`: decision log
- `docs/part1-architecture.md`: architecture

Never invent a table or column. Gold row counts will not match the warehouse backup. This OLTP has 121,317 order lines. The backup's internet and reseller facts add up to 121,253.

Banned names: `Person.Contact`, `Sales.Individual`, `CustomerAddress`, `EmployeeAddress`, `StoreContact`, `VendorContact`, `ContactCreditCard`, `Employee.ManagerID`, `Sales.Customer.CustomerType`. `Person.ContactType` is a real table and is not a Gold input.

## 3. Naming

| Item | Name |
|---|---|
| Lakehouses | `lh_AdventureWorks_Bronze`, `lh_AdventureWorks_Silver` |
| Warehouse | `wh_AdventureWorks_Gold` |
| Silver entities | `cleansed.<Entity>` |
| Silver logs | `etl.quarantine`, `etl.dq_result`, `etl.load_log` |
| Gold | `DimXxx`, `FactXxx` |
| Surrogate | `<Entity>Key`. Business keys keep the source name |
| Audit | `dbo.ETL_Log` |
| Watermark | `dbo.ingest_watermark` |
| Load | `dbo.usp_Load_Gold` |

No `Silver_` prefix.

## 4. Bronze

Raw landing. Source schema and table names. The control query is `sql/source/ingest_control.sql`. It is read-only. `fabric_user` stays `db_datareader`.

Excluded: the `cdc` schema, `dbo.AWBuildVersion`, `dbo.sysdiagrams`, `dbo.systranschemas`, `Person.Password`, and views.

Type serialization in that query, and nowhere else: geography to WKT plus SRID, `hierarchyid` to string, `xml` to `nvarchar(max)`, alias types cast from `sys.types`, `varbinary` / `binary` / `image` omitted. Computed columns are selected as stored values.

`is_core = 1` is the Silver input list. Everything else is copied and then ignored. Default load is full overwrite. Incremental upsert is only `Sales.SalesOrderHeader` and `Sales.SalesOrderDetail`.

Never put credentials in code or docs.

## 5. Silver

One Fabric Runtime 2.0 notebook. Read Bronze, write `cleansed` tables for Gold inputs only.

`SalesOrderLineNumber` is `ROW_NUMBER()` within `SalesOrderID` ordered by `SalesOrderDetailID`. It is not `SalesOrderDetailID`. Keep `SalesOrderDetailID` for reconciliation.

Drop `rowguid` and `ModifiedDate`, except `ModifiedDate` on the two watermark tables. Drop `CardNumber`, `NationalIDNumber`, `LoginID`, and `BirthDate`.

Money is `DecimalType(19,4)`. Nulls use a documented default. Do not drop rows silently. Deduplicate on the business key. Rejects go to `etl.quarantine`.

`DimCustomer` is `Sales.Customer` where `StoreID` is null. `DimReseller` is `Sales.Store`. Geography is distinct city, state, and country, reached through `Person.BusinessEntityAddress`. One address per owner. Address-type priority is fixed from the six `AddressType` names after they are read, not guessed.

V-Order on. No partitioning, Z-order, or liquid clustering. A failed table is logged and must not disappear silently.

## 6. Gold

`dbo.usp_Load_Gold` is one transaction. Keys are declared `NOT ENFORCED`. The load rejects duplicates. Unknown member is `-1`.

`FactInternetSales` is `OnlineOrderFlag = 1`. `FactResellerSales` is `OnlineOrderFlag = 0`. Both use primary key `(SalesOrderNumber, SalesOrderLineNumber)`.

`FactInternetSalesReason` primary key is `(SalesOrderNumber, SalesOrderLineNumber, SalesReasonKey)`. The OLTP table is header grain, 27,647 rows, key `(SalesOrderID, SalesReasonID)`. Stamp each reason onto every line of that internet order. `DimSalesReason.SalesReasonAlternateKey` is `SalesReasonID`.

`PromotionKey` is on both line facts, from `SalesOrderDetail.SpecialOfferID`.

`UnitPriceDiscount` is a rate. `DiscountAmount = UnitPrice * OrderQty * UnitPriceDiscount`. `SalesAmount` is recomputed as `decimal(19,4)`. `TotalProductCost = unit cost * OrderQty`. Unit cost is `ProductCostHistory` as of `OrderDate`, else `Product.StandardCost`.

`TaxAmt` and `Freight` are allocated by the line's share of header `SubTotal`. Line sums must equal the header. A zero subtotal keeps both amounts on the first line.

A null `CurrencyRateID` maps to USD only after a query shows those orders are USD. Until then, quarantine the rows.

Log `OnlineOrderFlag` versus `StoreID` mismatches. Do not fail the load on that check until the rate is measured.

Do not build `FactFinance`, `FactCallCenter`, `FactSurveyResponse`, or a daily inventory fact.

## 7. Trial

One Spark notebook per pipeline run. Runtime 2.0. Starter pool. No custom warm pool. Copy batch count 4. Do not schedule the pipeline. Dataflow Gen2 is not used.
