-- Sample Data for JOBORDER Table
-- Database: JOBORDER
-- Server: localhost:1436
-- Username: sa
-- Password: Snc@min123

INSERT INTO JOBORDER (
    MAT_TYPE, MAT_GROUP, SAP_ID, PART_NO, PART_NAME, 
    PRD_QTY, QTY_BOM, QTY_REQ, QTY_RECEIVED, PD_REQ, 
    PD01, PD09, WIP_QTY, REQ_PART, PD02, PD04, 
    STOCK_MAIN, STOCK_NG, STOCK_UNPACK, STOCK_SAFETY
) VALUES 
('Local', 'Foam', '10030059', '16320300000732', '16320300000732 Top foam', 
 900, 1, 900, 0, 0, 
 0, 0, 0, 0, 0, 0, 
 209454, 0, 0, 0),

('Local', 'Foam', '10031549', '12820300000540', 'Volute shell (above)12820300000540', 
 900, 1, 900, 0, 0, 
 0, 0, 0, 0, 0, 0, 
 140384, 0, 0, 0),

('SKD', 'Accessory/fitting', '20004212', '10500908000118', 'ADHESIVE 10500908000118', 
 900, 0.12, 108, 108, 0, 
 0, 0, 0, 0, 0, 0, 
 0, 0, 2640, 0),

('SKD', 'Accessory/fitting', '20004344', '16120300A34256', 'After-sales service card16120300A34256', 
 900, 1, 900, 900, 0, 
 0, 0, 0, 0, 0, 0, 
 0, 0, 16600, 0),

('SKD', 'Accessory/fitting', '10031460', '16020300A32262', 'Backside trademark16020300A32262', 
 900, 1, 900, 900, 0, 
 0, 0, 0, 0, 0, 0, 
 0, 0, 16600, 0);