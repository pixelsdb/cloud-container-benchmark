package io.pixelsdb.ccb.network;

import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * @author hank
 * @create 2025-09-20
 */
public interface Receiver extends AutoCloseable
{
    ByteBuffer receive(int bytes) throws IOException;

    boolean isClosed();
}
