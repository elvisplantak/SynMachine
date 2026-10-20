BEGIN TRANSACTION;
CREATE TABLE hardware_owner (
        slot INTEGER PRIMARY KEY CHECK(slot=1), sequence_id TEXT
    );
INSERT INTO "hardware_owner" VALUES(1,NULL);
CREATE TABLE hardware_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'BLOCKED', 'COMPLETED'))
    );
INSERT INTO "hardware_sequences" VALUES('dry-bootstrap-probe','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.sf.14d34e51-4755-48f8-afb4-c3eb5780ebd2','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.c5da6b0e-8a19-42a6-b097-f1fd67ff56aa','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.a8587cf6-64af-4da0-80c1-51f276be48dd','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.16a8b4e5-3a66-4945-ae74-80dcd020446b','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.4c030709-3939-4db5-b100-03a46f6b7d06','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.b5e92b47-9319-405d-97c3-5c683c0feccc','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.88716e80-2765-4f85-9859-1843394c970e','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.27966a1b-74ef-44ca-b8d7-bc5abe656147','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.a70a51ea-156a-4e59-80a4-d69831c4be57','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.f734abb6-626d-41ff-a181-2af5ad2ff797','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.78e29e52-327b-49cc-adc3-a719b41ea0e4','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.15932562-707c-4570-94f7-1d84f87aea47','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.f3a32323-d91b-49a4-85c7-d076ac6c2f81','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.868ab72b-a3b7-444e-a2c8-2041c98fddc1','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.9f8808cf-473d-4761-a02c-65d497acd3fd','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.aedd622f-16c2-44b3-b91e-15b811019de8','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.6a7b9e20-460f-41dd-aec8-3ce9d75f2fce','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.0a41eceb-914d-4811-b71c-c5fe259e46bf','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.a41307c5-ef69-4346-94a0-136296be7920','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.90cc473a-149d-4557-9ec2-3266d85499b9','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.f7d6579d-3fe3-4faf-bdc7-3835db2ba884','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.c67b8c70-a604-4ea2-8729-2c75f1134baf','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('service.arduino.9c506042-987e-440f-abbf-2c99c05d8806','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('568e281a-9c31-4518-bfe3-8b9686d9cc93','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('caeb14d5-2987-4698-bb67-54243a2daa01','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('3e477641-30b2-4939-94a5-798895c46a76','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('5f8b3f3f-727b-4bab-984d-65bfe3b50aaa','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('b8b18546-b224-4d14-ad0c-59559f3eb062','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('2234d0a0-5cbf-4824-9552-9a015a2a5c72','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('8c77bd99-4f78-41a9-b06f-33f478c7be68','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('74fa8771-1219-4190-9102-faec4fada290','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('fc637a95-c586-4b58-9d1d-6d8864e8434b','COMPLETED');
INSERT INTO "hardware_sequences" VALUES('bf015f83-9212-4813-a5dd-8a1d52b65160','COMPLETED');
CREATE TABLE ownership_identity (id TEXT NOT NULL);
INSERT INTO "ownership_identity" VALUES('283daa20-c23e-4822-86b9-1d2acc99f02d');
COMMIT;
