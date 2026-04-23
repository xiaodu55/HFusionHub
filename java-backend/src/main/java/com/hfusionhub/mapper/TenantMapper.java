package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Tenant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface TenantMapper extends BaseMapper<Tenant> {

    Tenant selectBySlug(@Param("slug") String slug);

    List<Tenant> selectByUserId(@Param("userId") Long userId);
}
