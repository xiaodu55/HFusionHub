import java.sql.*;

/**
 * DolphinScheduler standalone(H2 文件库)首次启动的 schema 自动初始化。
 *
 * 背景: 3.2.1 standalone 的 H2 为 mem 库时元数据随重启清空;改文件库后
 * 空库启动会因缺表直接退出(t_ds_worker_group not found)。本类带守卫:
 * 仅当库为空(无 t_ds_user)时执行 RUNSCRIPT,由 compose 的启动命令在
 * start.sh 之前调用一次,之后跳过。
 *
 * 编译: 由容器内 javac 编译到 data 卷(compose command 处理,无需手工)。
 */
public class Init {
    public static void main(String[] args) throws Exception {
        Connection c = DriverManager.getConnection(
                "jdbc:h2:file:/opt/dolphinscheduler/data/h2db/dolphinscheduler;MODE=MySQL;AUTO_SERVER=TRUE",
                "sa", "");
        boolean empty;
        try (Statement s = c.createStatement();
             ResultSet rs = s.executeQuery("SELECT count(*) FROM t_ds_user")) {
            rs.next();
            empty = rs.getInt(1) == 0;
        } catch (Exception e) {
            empty = true;  // 表不存在 = 空库
        }
        if (empty) {
            Statement s = c.createStatement();
            s.execute("RUNSCRIPT FROM '/opt/dolphinscheduler/conf/sql/dolphinscheduler_h2.sql'");
            System.out.println("SCHEMA INIT OK");
        } else {
            System.out.println("SCHEMA EXISTS, skip init");
        }
    }
}
