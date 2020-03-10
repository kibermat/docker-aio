-- To create the database:
--   CREATE DATABASE blog;
--   CREATE USER blog WITH PASSWORD 'blog';
--   GRANT ALL ON DATABASE blog TO blog;
--
-- To reload the tables:
--   psql -U blog -d blog < schema.sql

CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    report VARCHAR(1024),
    published TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
