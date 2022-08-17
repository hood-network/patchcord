UPDATE messages
    SET message_type = 19
    WHERE message_type = 0 and not message_reference::text = '{}';
