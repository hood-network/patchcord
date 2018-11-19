CREATE TABLE IF NOT EXISTS instance_invites (
    code text PRIMARY KEY,

    created_at timestamp without time zone default (now() at time zone 'utc'),

    uses bigint DEFAULT 0,
    max_uses bigint DEFAULT -1
);
