UPDATE icons 
    SET hash = 'a_78f36f55ba85d65b.' || REPLACE (hash, '#a_', '')
    WHERE hash LIKE '#a_%';

UPDATE icons 
    SET hash = '78f36f55ba85d65b.' || REPLACE (hash, '#', '')
    WHERE hash NOT LIKE '%a_%';
