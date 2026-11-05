CREATE TABLE IF NOT EXISTS sets (
  id INTEGER PRIMARY KEY,
  zip_name TEXT UNIQUE,
  tournament TEXT,
  event TEXT,
  phase TEXT,
  round_text TEXT,
  best_of INTEGER,
  p1_name TEXT, p1_chars TEXT, p1_score INTEGER,
  p2_name TEXT, p2_chars TEXT, p2_score INTEGER,
  duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY,
  set_id INTEGER REFERENCES sets(id),
  file_name TEXT,
  game_number INTEGER,
  stage TEXT,
  frames INTEGER,
  duration_sec REAL,
  end_method TEXT,
  p1_name TEXT, p1_port INTEGER, p1_char TEXT, p1_stocks_left INTEGER, p1_damage REAL,
  p2_name TEXT, p2_port INTEGER, p2_char TEXT, p2_stocks_left INTEGER, p2_damage REAL,
  winner TEXT
);

CREATE INDEX IF NOT EXISTS idx_games_set ON games(set_id);
CREATE INDEX IF NOT EXISTS idx_games_stage ON games(stage);
