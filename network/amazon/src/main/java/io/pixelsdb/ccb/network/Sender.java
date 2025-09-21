package io.pixelsdb.ccb.network;

import java.io.IOException;

/**
 * @author hank
 * @create 2025-09-20
 */
public interface Sender extends AutoCloseable
{
    void send(byte[] buffer) throws IOException;

    boolean isClosed();

    @Override
    void close() throws IOException;
}
