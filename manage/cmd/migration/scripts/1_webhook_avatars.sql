-- webhook_avatars table. check issue 46.
CREATE TABLE IF NOT EXISTS webhook_avatars (
    webhook_id bigint,

    -- this is e.g a sha256 hash of EmbedURL.to_md_url
    hash text,

    -- we don't hardcode the mediaproxy url here for obvious reasons.
    -- the output of EmbedURL.to_md_url goes here.
    md_url_redir text,

    PRIMARY KEY (webhook_id, hash)
);
