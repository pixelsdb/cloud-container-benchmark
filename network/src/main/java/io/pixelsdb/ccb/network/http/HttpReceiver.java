package io.pixelsdb.ccb.network.http;

import io.pixelsdb.ccb.network.Receiver;
import io.pixelsdb.pixels.common.physical.PhysicalReader;
import io.pixelsdb.pixels.common.physical.PhysicalReaderUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;

import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * @author hank
 * @create 2025-09-20
 */
public class HttpReceiver implements Receiver
{
    private final PhysicalReader physicalReader;
    private boolean closed = false;

    public HttpReceiver(String host, int port) throws IOException
    {
        Storage httpStream = StorageFactory.Instance().getStorage(Storage.Scheme.httpstream);
        String path = Storage.Scheme.httpstream + "://" + host + ":" + port;
        this.physicalReader = PhysicalReaderUtil.newPhysicalReader(httpStream, path);
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        return this.physicalReader.readFully(bytes);
    }

    @Override
    public boolean isClosed()
    {
        return this.closed;
    }

    @Override
    public void close() throws IOException
    {
        this.physicalReader.close();
        this.closed = true;
    }
}
