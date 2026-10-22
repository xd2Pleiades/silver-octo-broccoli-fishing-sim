The historic v13.1.34 project did not yet have an official career-save format.
For that reason, M10 cannot claim to migrate a genuine v13.1.34 save file. The
v13.2.07 tests instead use synthetic legacy-state fixtures for individual
fields and explicitly test the current schema, checksum, backup and unknown
schema behavior. A true legacy-save migration fixture can be added if an actual
older save artifact becomes available.
