# DBEAVER - PostgreSQL

Assume that we have already establish the database connection in `DBEAVER`.

If not, follow these steps to create **USER** and the **DATABASE** on postgres [Assumed that you have **installed Postgresql** on your computer] :

```bash
sudo -u postgres psql

CREATE USER user_name WITH PASSWORD 'user_password';
CREATE DATABASE user_db OWNER user_name;
GRANT ALL PRIVILEGES ON DATABASE user_db TO user_name;
```

So, in `DBEAVER`, you can select the **Database** button to establish a **New connection** to the database that you've created above.

```plaintext
Database : user_db
username : user_name
password : user_password
```

## Initialization

