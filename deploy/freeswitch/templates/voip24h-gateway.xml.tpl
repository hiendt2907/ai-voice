<include>
  <gateway name="voip24h">
    <param name="username" value="${SIP_EXTENSION}"/>
    <param name="password" value="${SIP_PASSWORD}"/>
    <param name="realm" value="${SIP_SERVER}"/>
    <param name="proxy" value="${SIP_SERVER}"/>
    <param name="register" value="true"/>
    <param name="register-transport" value="udp"/>
    <param name="expire-seconds" value="600"/>
    <param name="retry-seconds" value="30"/>
    <param name="caller-id-in-from" value="true"/>
    <param name="extension-in-contact" value="true"/>
    <param name="ping" value="25"/>
  </gateway>
</include>
