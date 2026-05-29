  CREATE TABLE users (                                                                                                                                                                                                                        
      id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      email           TEXT NOT NULL UNIQUE,
      hashed_password TEXT NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  CREATE TABLE recipes (                                                                                                                                                                                                                      
      id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      owner_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,                                                                                                                                                             
      created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at          TIMESTAMPTZ,
      title               TEXT NOT NULL,
      description         TEXT,
      ingredients         JSONB NOT NULL,
      steps               TEXT[] NOT NULL,
      tools               TEXT[],
      tags                TEXT[],
      difficulty          TEXT,
      prep_time           INTEGER,
      cook_time           INTEGER,
      servings            INTEGER NOT NULL,
      cost_per_serving    NUMERIC(7,2),
      nutrition_per_serving JSONB,
      source_url          TEXT
  );