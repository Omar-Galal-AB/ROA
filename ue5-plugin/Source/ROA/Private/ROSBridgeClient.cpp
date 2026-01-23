// Copyright ROA Development Team. All Rights Reserved.

#include "ROSBridgeClient.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

DEFINE_LOG_CATEGORY(LogROSBridge);

FROSBridgeClient::FROSBridgeClient()
    : Socket(nullptr)
    , Thread(nullptr)
    , bIsRunning(false)
    , bStopRequested(false)
    , bConnected(false)
    , ServerPort(9876)
{
}

FROSBridgeClient::~FROSBridgeClient()
{
    Disconnect();
}

bool FROSBridgeClient::Connect(const FString& Host, int32 Port)
{
    if (bConnected)
    {
        UE_LOG(LogROSBridge, Warning, TEXT("Already connected"));
        return true;
    }

    ServerHost = Host;
    ServerPort = Port;

    // Create socket
    ISocketSubsystem* SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    if (!SocketSubsystem)
    {
        UE_LOG(LogROSBridge, Error, TEXT("Failed to get socket subsystem"));
        return false;
    }

    Socket = SocketSubsystem->CreateSocket(NAME_Stream, TEXT("ROSBridgeSocket"), false);
    if (!Socket)
    {
        UE_LOG(LogROSBridge, Error, TEXT("Failed to create socket"));
        return false;
    }

    // Resolve address
    TSharedRef<FInternetAddr> Addr = SocketSubsystem->CreateInternetAddr();
    bool bIsValid;
    Addr->SetIp(*Host, bIsValid);
    Addr->SetPort(Port);

    if (!bIsValid)
    {
        UE_LOG(LogROSBridge, Error, TEXT("Invalid host: %s"), *Host);
        SocketSubsystem->DestroySocket(Socket);
        Socket = nullptr;
        return false;
    }

    UE_LOG(LogROSBridge, Log, TEXT("Connecting to rosbridge at %s:%d..."), *Host, Port);

    // Connect (blocking)
    if (!Socket->Connect(*Addr))
    {
        UE_LOG(LogROSBridge, Error, TEXT("Failed to connect to %s:%d"), *Host, Port);
        SocketSubsystem->DestroySocket(Socket);
        Socket = nullptr;
        return false;
    }

    Socket->SetNonBlocking(true);
    bConnected = true;

    // Start receive thread
    Thread = FRunnableThread::Create(this, TEXT("ROSBridgeClient"), 0, TPri_Normal);

    UE_LOG(LogROSBridge, Warning, TEXT("? Connected to rosbridge at %s:%d - Bridge is UP!"), *Host, Port);
    
    // Send a test status request to verify bidirectional communication
    TSharedPtr<FJsonObject> StatusMsg = MakeShared<FJsonObject>();
    StatusMsg->SetStringField(TEXT("op"), TEXT("status"));
    StatusMsg->SetStringField(TEXT("level"), TEXT("info"));
    StatusMsg->SetStringField(TEXT("msg"), TEXT("UE5 ROA Plugin connected"));
    SendJson(StatusMsg);
    UE_LOG(LogROSBridge, Log, TEXT("Sent connection status message to rosbridge"));
    
    return true;
}

void FROSBridgeClient::Disconnect()
{
    bStopRequested = true;

    if (Thread)
    {
        Thread->WaitForCompletion();
        delete Thread;
        Thread = nullptr;
    }

    if (Socket)
    {
        Socket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
        Socket = nullptr;
    }

    bConnected = false;
    bStopRequested = false;
    UE_LOG(LogROSBridge, Log, TEXT("Disconnected from rosbridge"));
}

bool FROSBridgeClient::IsConnected() const
{
    return bConnected;
}

bool FROSBridgeClient::Advertise(const FString& Topic, const FString& Type)
{
    if (!bConnected)
    {
        return false;
    }

    TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
    Msg->SetStringField(TEXT("op"), TEXT("advertise"));
    Msg->SetStringField(TEXT("topic"), Topic);
    Msg->SetStringField(TEXT("type"), Type);

    UE_LOG(LogROSBridge, Log, TEXT("Advertising topic: %s (%s)"), *Topic, *Type);
    return SendJson(Msg);
}

bool FROSBridgeClient::Unadvertise(const FString& Topic)
{
    if (!bConnected)
    {
        return false;
    }

    TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
    Msg->SetStringField(TEXT("op"), TEXT("unadvertise"));
    Msg->SetStringField(TEXT("topic"), Topic);

    return SendJson(Msg);
}

bool FROSBridgeClient::Publish(const FString& Topic, TSharedPtr<FJsonObject> Message)
{
    if (!bConnected)
    {
        return false;
    }

    TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
    Msg->SetStringField(TEXT("op"), TEXT("publish"));
    Msg->SetStringField(TEXT("topic"), Topic);
    Msg->SetObjectField(TEXT("msg"), Message);

    return SendJson(Msg);
}

bool FROSBridgeClient::Subscribe(const FString& Topic, const FString& Type, TFunction<void(TSharedPtr<FJsonObject>)> Callback)
{
    if (!bConnected)
    {
        return false;
    }

    // Store callback
    {
        FScopeLock Lock(&CallbackLock);
        SubscriptionCallbacks.Add(Topic, Callback);
    }

    TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
    Msg->SetStringField(TEXT("op"), TEXT("subscribe"));
    Msg->SetStringField(TEXT("topic"), Topic);
    Msg->SetStringField(TEXT("type"), Type);

    UE_LOG(LogROSBridge, Log, TEXT("Subscribing to topic: %s (%s)"), *Topic, *Type);
    return SendJson(Msg);
}

bool FROSBridgeClient::Unsubscribe(const FString& Topic)
{
    if (!bConnected)
    {
        return false;
    }

    {
        FScopeLock Lock(&CallbackLock);
        SubscriptionCallbacks.Remove(Topic);
    }

    TSharedPtr<FJsonObject> Msg = MakeShared<FJsonObject>();
    Msg->SetStringField(TEXT("op"), TEXT("unsubscribe"));
    Msg->SetStringField(TEXT("topic"), Topic);

    return SendJson(Msg);
}

bool FROSBridgeClient::SendJson(TSharedPtr<FJsonObject> JsonObj)
{
    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);

    // Add newline delimiter
    OutputString += TEXT("\n");

    // Queue for sending
    OutgoingMessages.Enqueue(OutputString);
    return true;
}

// FRunnable interface
bool FROSBridgeClient::Init()
{
    bIsRunning = true;
    return true;
}

uint32 FROSBridgeClient::Run()
{
    UE_LOG(LogROSBridge, Log, TEXT("ROSBridge receiver thread started"));

    while (!bStopRequested)
    {
        // Send queued messages
        FString OutMsg;
        while (OutgoingMessages.Dequeue(OutMsg))
        {
            if (Socket)
            {
                FTCHARToUTF8 Converter(*OutMsg);
                int32 BytesSent = 0;
                Socket->Send((const uint8*)Converter.Get(), Converter.Length(), BytesSent);
                
                if (BytesSent > 0)
                {
                    UE_LOG(LogROSBridge, Log, TEXT(">>> SENT %d bytes to rosbridge"), BytesSent);
                }
                else
                {
                    UE_LOG(LogROSBridge, Warning, TEXT("Failed to send message to rosbridge"));
                }
            }
        }

        // Receive data
        ProcessIncomingData();

        // Sleep briefly
        FPlatformProcess::Sleep(0.001f); // 1ms
    }

    UE_LOG(LogROSBridge, Log, TEXT("ROSBridge receiver thread stopped"));
    return 0;
}

void FROSBridgeClient::Stop()
{
    bStopRequested = true;
}

void FROSBridgeClient::Exit()
{
    bIsRunning = false;
}

void FROSBridgeClient::ProcessIncomingData()
{
    if (!Socket)
    {
        return;
    }

    uint32 PendingDataSize = 0;
    if (Socket->HasPendingData(PendingDataSize) && PendingDataSize > 0)
    {
        TArray<uint8> ReceivedData;
        ReceivedData.SetNumUninitialized(PendingDataSize);

        int32 BytesRead = 0;
        if (Socket->Recv(ReceivedData.GetData(), ReceivedData.Num(), BytesRead))
        {
            UE_LOG(LogROSBridge, Log, TEXT("<<< RECEIVED %d bytes from rosbridge"), BytesRead);
      
            ReceivedData.Add(0); // Null terminate
            FString ReceivedString = UTF8_TO_TCHAR(ReceivedData.GetData());
            ReceiveBuffer += ReceivedString;

            // Process complete messages (newline delimited)
            int32 NewlineIndex;
            while (ReceiveBuffer.FindChar('\n', NewlineIndex))
            {
                FString Line = ReceiveBuffer.Left(NewlineIndex);
                ReceiveBuffer = ReceiveBuffer.Mid(NewlineIndex + 1);

                if (!Line.IsEmpty())
                {
                    UE_LOG(LogROSBridge, Log, TEXT("Processing message: %s"), *Line.Left(200));
                    HandleMessage(Line);
                }
            }
        }
    }
}

void FROSBridgeClient::HandleMessage(const FString& JsonString)
{
    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);

    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
    {
        UE_LOG(LogROSBridge, Warning, TEXT("Failed to parse JSON: %s"), *JsonString);
        return;
    }

    FString Op = JsonObj->GetStringField(TEXT("op"));

    if (Op == TEXT("publish"))
    {
        // Incoming message from subscribed topic
        FString Topic = JsonObj->GetStringField(TEXT("topic"));
        TSharedPtr<FJsonObject> Msg = JsonObj->GetObjectField(TEXT("msg"));

        FScopeLock Lock(&CallbackLock);
        if (SubscriptionCallbacks.Contains(Topic))
        {
            SubscriptionCallbacks[Topic](Msg);
        }
    }
    else if (Op == TEXT("status"))
    {
        FString Level = JsonObj->GetStringField(TEXT("level"));
        FString StatusMsg = JsonObj->GetStringField(TEXT("msg"));
        UE_LOG(LogROSBridge, Log, TEXT("rosbridge status [%s]: %s"), *Level, *StatusMsg);
    }
}
