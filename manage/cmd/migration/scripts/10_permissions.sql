-- channel_overwrites table already has allow and deny as bigints.
alter table roles
    alter column permissions type bigint;
